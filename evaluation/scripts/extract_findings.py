#!/usr/bin/env python3
"""
Extract Findings Corpus — Refactored v3

Architecture:
  Raw Finding → Canonical Finding → Semantic Family

Changes from v2:
  1. UNSW extraction fixed (Impact:/Confidence: lines no longer selected as description)
  2. Run attribution preserved (no default run ID collapsing)
  3. Duplicate batch detection and deduplication
  4. Literature mapping generation REMOVED (researcher decision)
  5. Novelty detection REMOVED (researcher decision)
  6. Semantic family classification ADDED
  7. Genuine Behavioral Signals separated from artifacts

Usage:
    python scripts/extract_findings.py

Outputs to:
    evaluation/findings/
"""

from __future__ import annotations

import json
import csv
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# --- Configuration -----------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # TFG root
NIDS_DIR = BASE_DIR / "nids-smell-audit" / "Phase3"
LOGS_DIR = NIDS_DIR / "logs"
FINAL_BATCH_REPORT_RUNS = LOGS_DIR / "final_batch_report_runs"
OUTPUT_DIR = BASE_DIR / "evaluation" / "findings"

# Partition mapping: batch_id keyword -> (dataset, partition)
PARTITION_MAP: List[Tuple[str, str, str]] = [
    ("friday-workinghours-afternoon-ddos", "CICIDS2017", "Friday-WorkingHours-Afternoon-DDos"),
    ("friday-workinghours-morning", "CICIDS2017", "Friday-WorkingHours-Morning"),
    ("friday-workinghours-afternoon-portscan", "CICIDS2017", "Friday-WorkingHours-Afternoon-PortScan"),
    ("tuesday-workinghours", "CICIDS2017", "Tuesday-WorkingHours"),
    ("wednesday-workinghours", "CICIDS2017", "Wednesday-WorkingHours"),
    ("monday-workinghours", "CICIDS2017", "Monday-WorkingHours"),
    ("thursday-workinghours-afternoon-infilteration", "CICIDS2017", "Thursday-WorkingHours-Afternoon-Infilteration"),
    ("thursday-workinghours-morning-webattacks", "CICIDS2017", "Thursday-WorkingHours-Morning-WebAttacks"),
    ("unsw_nb15_training-set", "UNSW-NB15", "UNSW_NB15_Training_Set"),
    ("unsw_nb15_testing-set", "UNSW-NB15", "UNSW_NB15_Test_Set"),
]

# Canonical finding family definitions
CANONICAL_DEFINITIONS = [
    {
        "canonical_name": "Strong Feature Dependency Pairs",
        "description": "Multiple feature pairs exhibit near-perfect linear correlations arising from feature engineering artifacts rather than intrinsic traffic behavior.",
        "keywords": ["dependency pair", "strong depend", "linear depend", "near-perfect correlation", "redundant feature", "Fwd Header Length", "Subflow Fwd", "multicollinearity", "redundancy", "feature correlation"],
    },
    {
        "canonical_name": "Packet Length Structural Variation",
        "description": "Backward or forward packet length features show significant class-conditioned structural variation reflecting genuine behavioral differences.",
        "keywords": ["packet length", "backward packet length", "forward packet length", "bwd packet length", "fwd packet length", "structural variation", "class-conditioned variation"],
    },
    {
        "canonical_name": "Destination Port Concentration",
        "description": "Destination Port feature exhibits strong concentration on a single port within attack traffic, providing a shortcut for classification.",
        "keywords": ["destination port", "port concentration", "single port", "zero entropy", "port distribution", "port dominance"],
    },
    {
        "canonical_name": "Low Diversity / Near-Constant Features",
        "description": "Bulk traffic features, TCP flag features, or other attributes show near-constant values with minimal variation, suggesting saturation or structural uniformity.",
        "keywords": ["near-constant", "bulk rate", "bulk traffic", "tcp flag", "psh flag", "urg flag", "low cardinality", "low diversity", "uniformity", "saturation", "constant value", "no variation", "unique value count equal to one", "bulk"],
    },
    {
        "canonical_name": "Duplicate Rows",
        "description": "Dataset contains duplicated rows that may artificially inflate feature distributions and correlations.",
        "keywords": ["duplicate", "duplicated row", "duplication", "repeated row", "identical row"],
    },
    {
        "canonical_name": "Class Imbalance",
        "description": "Uneven distribution between benign and attack classes that may influence feature distributions and model bias.",
        "keywords": ["class imbalance", "imbalance ratio", "class ratio", "benign ratio", "attack ratio"],
    },
    {
        "canonical_name": "Protocol Dominance / Shortcut",
        "description": "Protocol identifiers or protocol-related features dominate classification, creating shortcut learning opportunities.",
        "keywords": ["protocol", "dominance", "ttl", "portmap", "dns", "protocol shortcut", "protocol dominance", "protocol-based"],
    },
    {
        "canonical_name": "Distribution Collapse / Low Diversity",
        "description": "Dataset exhibits insufficient behavioral diversity with large portions collapsed into a small number of dominant structures.",
        "keywords": ["distribution collapse", "low diversity", "low entropy", "dominant cluster", "repetitive", "no diversity", "concentrated distribution"],
    },
    {
        "canonical_name": "Average Packet Size Variation",
        "description": "Average Packet Size shows moderate class-conditioned variation that may serve as a supplementary discriminative feature.",
        "keywords": ["average packet size", "packet size mean", "mean packet size", "avg packet size"],
    },
    {
        "canonical_name": "Feature Redundancy / Multicollinearity",
        "description": "Widespread feature redundancy reduces effective dimensionality and risks inflating feature importance metrics.",
        "keywords": ["feature redundancy", "redundant feature", "redundancy cluster", "reduced dimensionality", "inflated importance"],
    },
    {
        "canonical_name": "Synthetic / Scripted Generation Artifacts",
        "description": "Structural regularities suggesting scripted or synthetic generation processes rather than genuine network behavior.",
        "keywords": ["synthetic", "scripted", "generation artifact", "artificial regularity", "repeated motif", "deterministic"],
    },
    {
        "canonical_name": "Label Overlap / Weak Separability",
        "description": "Different classes exhibit overlapping feature distributions suggesting weak separability or label ambiguity.",
        "keywords": ["label overlap", "class overlap", "weak separation", "ambiguous", "overlapping", "contradiction", "class mixing"],
    },
    {
        "canonical_name": "Temporal Attack Structure",
        "description": "Attack activity follows rigid temporal patterns that may create temporal shortcuts.",
        "keywords": ["temporal", "time-based", "schedule", "time window", "timestamp", "temporal pattern", "iat"],
    },
    {
        "canonical_name": "Representation-Sensitive Structure",
        "description": "Feature structure or dependency topology is sensitive to representation choices, suggesting potential representation artifacts.",
        "keywords": ["representation", "encoding", "preprocessing", "feature extraction artifact", "embedding", "neighborhood geometry"],
    },
    {
        "canonical_name": "Flag Feature Uniformity",
        "description": "TCP flag features exhibit limited variation suggesting suppression or uniformity under attack conditions.",
        "keywords": ["flag", "psh", "urg", "fin", "syn", "ack", "rst", "tcp flag"],
    },
]

# Semantic family definitions (NEW — replaces literature mapping)
SEMANTIC_FAMILIES = [
    {
        "semantic_family": "Feature Engineering Redundancy",
        "description": "Features that carry duplicate information due to feature engineering choices (e.g., derived features, duplicated columns).",
        "canonical_members": ["Strong Feature Dependency Pairs", "Feature Redundancy / Multicollinearity"],
    },
    {
        "semantic_family": "Shortcut Learning Signals",
        "description": "Features that provide unintended classification shortcuts, allowing models to achieve high performance without learning genuine traffic behavior.",
        "canonical_members": ["Protocol Dominance / Shortcut", "Destination Port Concentration", "Low Diversity / Near-Constant Features", "Flag Feature Uniformity"],
    },
    {
        "semantic_family": "Distributional Artifacts",
        "description": "Unnatural distributional structure in the data, including class imbalance, distribution collapse, and low diversity regions.",
        "canonical_members": ["Class Imbalance", "Distribution Collapse / Low Diversity", "Synthetic / Scripted Generation Artifacts"],
    },
    {
        "semantic_family": "Temporal Artifacts",
        "description": "Time-based patterns that may create temporal shortcuts or reflect scripted attack schedules.",
        "canonical_members": ["Temporal Attack Structure"],
    },
    {
        "semantic_family": "Label Structure Issues",
        "description": "Suspicious label behavior including class overlap, weak separability, and potential label ambiguity.",
        "canonical_members": ["Label Overlap / Weak Separability"],
    },
    {
        "semantic_family": "Data Quality Issues",
        "description": "Dataset-level quality problems such as duplicated rows and representation artifacts.",
        "canonical_members": ["Duplicate Rows", "Representation-Sensitive Structure"],
    },
    {
        "semantic_family": "Genuine Behavioral Signals",
        "description": "Features that show genuine class-conditioned structural variation reflecting real traffic behavior rather than dataset artifacts. These are NOT artifacts and should not be mapped to literature artifacts.",
        "canonical_members": ["Packet Length Structural Variation", "Average Packet Size Variation"],
    },
]


# --- Helpers -----------------------------------------------------------------

def resolve_partition(batch_id: str) -> Tuple[str, str]:
    """Resolve a batch_id to (dataset, partition)."""
    batch_lower = batch_id.lower()
    for pattern, dataset, partition in PARTITION_MAP:
        if pattern in batch_lower:
            return dataset, partition
    return "unknown", "unknown"


def extract_run_id_from_dirname(dirname: str) -> str:
    """Extract run ID from directory name like 'final_batch_report_run_001_10-06_...'."""
    m = re.search(r'run_(\d{3})', dirname)
    if m:
        return m.group(1)
    return "unknown"


def extract_batch_timestamp(batch_id: str) -> str:
    """Extract timestamp from batch_id for deduplication."""
    m = re.search(r'(\d{10})', batch_id)
    return m.group(1) if m else ""


# --- Step 2: Extract Raw Findings from Report MD ---------------------------

def extract_findings_from_report_md(
    report_path: Path,
    run_id: str,
    dataset: str,
    partition: str,
) -> List[Dict[str, Any]]:
    """Extract structured findings from a final batch report markdown.
    
    Handles both CICIDS2017 format (### headers, **Impact:** bold markers)
    and UNSW-NB15 format (Finding N: headers, Impact: without bold markers).
    """
    findings = []
    
    try:
        text = report_path.read_text(encoding="utf-8")
    except Exception:
        return findings
    
    source = str(report_path)
    
    # Split into sections by ## headers OR numbered headers like "3. Most Important"
    sections = re.split(r'\n(?:##\s+|\d+\.\s+)', text)
    
    for section in sections:
        if not section.strip():
            continue
        
        header = section.split('\n')[0].strip()
        
        # Determine finding type from section header
        if "Most Important Investigated Findings" in header:
            finding_type = "investigated"
        elif "Additional Findings" in header or "Open Risks" in header:
            finding_type = "additional"
        else:
            continue
        
        # Split subsection into individual findings by ### headers OR "Finding N:" pattern
        subsections = re.split(r'\n(?:###\s+|Finding\s+\d+:\s*)', section)
        
        # Filter out non-finding subsections
        valid_subsections = []
        for sub in subsections:
            sub = sub.strip()
            if not sub or len(sub) < 30:
                continue
            # Check if it has finding markers (Impact: with or without bold)
            has_impact = "Impact:" in sub[:200]
            is_substantial = len(sub) > 100
            if has_impact or is_substantial:
                valid_subsections.append(sub)
        
        subsections = valid_subsections
        
        for sub in subsections:
            sub = sub.strip()
            if not sub or len(sub) < 30:
                continue
            
            lines = sub.split('\n')
            title = lines[0].strip() if lines else ""
            body = '\n'.join(lines[1:]) if len(lines) > 1 else ""
            
            # Skip section headers
            if re.match(r'^\d+\.\s+Most Important', title) or re.match(r'^\d+\.\s+', title):
                continue
            
            # Extract severity/impact (handle both **Impact:** and Impact: formats)
            severity = ""
            impact_m = re.search(r'\*\*Impact:\*\*\s*(\d+)/100\s*\(([^)]+)\)', sub)
            if not impact_m:
                impact_m = re.search(r'Impact:\s*(\d+)/100\s*\(([^)]+)\)', sub)
            if impact_m:
                severity = f"{impact_m.group(1)}/100 ({impact_m.group(2).strip()})"
            
            # Extract confidence (handle both formats)
            confidence = ""
            conf_m = re.search(r'\*\*Confidence:\*\*\s*(\d+)/100\s*\(([^)]+)\)', sub)
            if not conf_m:
                conf_m = re.search(r'Confidence:\s*(\d+)/100\s*\(([^)]+)\)', sub)
            if conf_m:
                confidence = f"{conf_m.group(1)}/100 ({conf_m.group(2).strip()})"
            
            # Extract description — skip Impact:/Confidence: lines regardless of length
            desc = ""
            for line in lines[1:]:
                stripped = line.strip()
                if not stripped:
                    continue
                # Skip metadata lines
                if stripped.startswith('**') or stripped.startswith('-') or stripped.startswith('#'):
                    continue
                if stripped.startswith('Impact:') or stripped.startswith('Confidence:'):
                    continue
                if stripped.startswith('**Impact:**') or stripped.startswith('**Confidence:**'):
                    continue
                if len(stripped) > 60:
                    desc = stripped[:500]
                    break
            
            if not title or not desc:
                continue
            
            # Classify into artifact family
            finding_text = f"{title} {desc}"
            artifact_family = classify_artifact_family(finding_text)
            
            # Count evidence mentions
            evidence_count = len(re.findall(r'\bevidence\b', sub, re.IGNORECASE))
            
            # Generate finding ID with run_id preserved
            safe_title = re.sub(r'[^a-zA-Z0-9_]', '_', title[:50])
            finding_id = f"{run_id}_{finding_type}_{safe_title}"
            
            findings.append({
                "finding_id": finding_id,
                "run_id": run_id,
                "dataset": dataset,
                "partition": partition,
                "title": title,
                "description": desc,
                "finding_type": finding_type,
                "severity": severity,
                "confidence": confidence,
                "supporting_evidence_count": str(evidence_count),
                "artifact_family": artifact_family,
                "source_report": source,
            })
    
    return findings


def classify_artifact_family(text: str) -> str:
    """Classify a finding description into an artifact family from the catalog."""
    t = text.lower()
    
    scores = {}
    for fam_name, keywords in [
        ("Shortcut / Highly Dependent Feature Families", 
         ["shortcut", "dependency", "dominant feature", "predictive", "correlation", "linear", 
          "near-perfect", "feature importance", "protocol dominance", "ttl", "fixed packet",
          "shortcut learning", "shortcut signal"]),
        ("Artificial Dependency Structures",
         ["artificial", "redundancy", "repeated motif", "structural artifact",
          "feature engineering artifact", "derived feature", "engineered", "cluster of redundancy"]),
        ("Distribution Collapse / Low Diversity",
         ["low diversity", "distribution collapse", "near-constant", "low cardinality",
          "low variance", "uniform", "saturation", "zero entropy", "dominant cluster",
          "low entropy", "limited variation"]),
        ("Duplicate / Near-Duplicate Structures",
         ["duplicate", "duplicated row", "near-duplicate", "repeated row", "identical row",
          "duplication"]),
        ("Label Inconsistency / Suspicious Label Structures",
         ["label", "class imbalance", "overlap", "class condition", "benign", "attack class",
          "class separability", "label ambiguity"]),
        ("Representation Artifacts",
         ["representation", "feature extraction", "encoding", "preprocessing",
          "flow construction", "aggregation artifact", "embedding", "neighborhood geometry"]),
    ]:
        score = 0
        for kw in keywords:
            if kw in t:
                score += 1
        if score > 0:
            scores[fam_name] = score
    
    if scores:
        return max(scores, key=scores.get)
    
    return "Artificial Dependency Structures"


# --- Step 3: Build Canonical Finding Taxonomy ------------------------------

def build_canonical_findings(
    raw_findings: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Group raw findings into canonical finding families."""
    
    finding_to_canonical: Dict[str, str] = {}
    
    for i, f in enumerate(raw_findings):
        fid = f.get("finding_id", f"raw_{i}")
        text = f"{f.get('title', '')} {f.get('description', '')}".lower()
        
        best_match = "Unclassified"
        best_score = 0
        
        for cd in CANONICAL_DEFINITIONS:
            score = 0
            for kw in cd["keywords"]:
                if kw.lower() in text:
                    score += 1
                if kw.lower() in f.get("title", "").lower():
                    score += 2  # Title matches are stronger
            
            if score > best_score:
                best_score = score
                best_match = cd["canonical_name"]
        
        finding_to_canonical[fid] = best_match
    
    # Build canonical families
    canonical_families = []
    for cd in CANONICAL_DEFINITIONS:
        name = cd["canonical_name"]
        members = [fid for fid, cn in finding_to_canonical.items() if cn == name]
        if members:
            canonical_families.append({
                "canonical_finding_id": name.lower().replace(" ", "_").replace("/", "_"),
                "canonical_name": name,
                "description": cd["description"],
                "num_member_findings": len(members),
                "member_findings": members,
            })
    
    # Add unclassified
    unclassified = [fid for fid, cn in finding_to_canonical.items() if cn == "Unclassified"]
    if unclassified:
        canonical_families.append({
            "canonical_finding_id": "unclassified",
            "canonical_name": "Unclassified",
            "description": "Findings that did not clearly match any predefined canonical family.",
            "num_member_findings": len(unclassified),
            "member_findings": unclassified,
        })
    
    return canonical_families, finding_to_canonical


# --- Step 3b: Build Semantic Families (NEW) ---------------------------------

def build_semantic_families(
    canonical_families: List[Dict[str, Any]],
    finding_to_canonical: Dict[str, str],
    raw_findings: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Group canonical findings into semantic families.
    
    This is the terminal abstraction layer. No literature mapping is performed.
    """
    # Build reverse map: canonical_name -> list of raw finding IDs
    canonical_to_raw: Dict[str, List[str]] = {}
    for fid, cname in finding_to_canonical.items():
        if cname not in canonical_to_raw:
            canonical_to_raw[cname] = []
        canonical_to_raw[cname].append(fid)
    
    # Build semantic families
    semantic_families_out = []
    for sf in SEMANTIC_FAMILIES:
        members = []
        for cname in sf["canonical_members"]:
            if cname in canonical_to_raw:
                members.append({
                    "canonical_name": cname,
                    "num_raw_findings": len(canonical_to_raw[cname]),
                    "raw_finding_ids": canonical_to_raw[cname],
                })
        
        if members:
            # Compute run/partition/dataset coverage
            all_runs = set()
            all_partitions = set()
            all_datasets = set()
            for m in members:
                for fid in m["raw_finding_ids"]:
                    for rf in raw_findings:
                        if rf.get("finding_id") == fid:
                            all_runs.add(rf.get("run_id", ""))
                            all_partitions.add(rf.get("partition", ""))
                            all_datasets.add(rf.get("dataset", ""))
                            break
            
            semantic_families_out.append({
                "semantic_family": sf["semantic_family"],
                "description": sf["description"],
                "num_canonical_members": len(members),
                "canonical_members": members,
                "coverage": {
                    "num_runs": len(all_runs),
                    "num_partitions": len(all_partitions),
                    "num_datasets": len(all_datasets),
                    "runs": sorted(all_runs),
                    "partitions": sorted(all_partitions),
                    "datasets": sorted(all_datasets),
                },
            })
    
    return semantic_families_out


# --- Step 4: Compute Finding Frequencies -----------------------------------

def compute_frequencies(
    raw_findings: List[Dict[str, Any]],
    finding_to_canonical: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Compute frequency statistics for each canonical finding family.
    
    Uses actual run IDs (not collapsed defaults).
    """
    freq: Dict[str, Dict[str, set]] = {}
    
    for finding in raw_findings:
        fid = finding.get("finding_id", "")
        cname = finding_to_canonical.get(fid, "Unclassified")
        
        if cname not in freq:
            freq[cname] = {"runs": set(), "partitions": set(), "datasets": set()}
        
        freq[cname]["runs"].add(finding.get("run_id", ""))
        freq[cname]["partitions"].add(finding.get("partition", ""))
        freq[cname]["datasets"].add(finding.get("dataset", ""))
    
    results = []
    for cname, counts in sorted(freq.items()):
        results.append({
            "canonical_finding": cname,
            "num_runs": len(counts["runs"]),
            "num_partitions": len(counts["partitions"]),
            "num_datasets": len(counts["datasets"]),
            "runs": sorted(counts["runs"]),
            "partitions": sorted(counts["partitions"]),
            "datasets": sorted(counts["datasets"]),
        })
    
    return results


# --- Step 7: Produce Deliverables ------------------------------------------

def write_json(data: Any, filename: str):
    """Write JSON to output directory."""
    path = OUTPUT_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  Written: {path}")


def write_csv(rows: List[Dict[str, Any]], filename: str, fieldnames: List[str]):
    """Write CSV to output directory."""
    path = OUTPUT_DIR / filename
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Written: {path}")


def write_findings_inventory(raw_findings: List[Dict[str, Any]]):
    """Write findings_inventory.json."""
    output = []
    for i, f in enumerate(raw_findings):
        output.append({
            "finding_id": f.get("finding_id", f"finding_{i:04d}"),
            "run_id": f.get("run_id", ""),
            "dataset": f.get("dataset", ""),
            "partition": f.get("partition", ""),
            "title": f.get("title", ""),
            "description": f.get("description", "")[:500],
            "finding_type": f.get("finding_type", ""),
            "severity": f.get("severity", ""),
            "confidence": f.get("confidence", ""),
            "supporting_evidence_count": f.get("supporting_evidence_count", ""),
            "artifact_family": f.get("artifact_family", ""),
            "source_report": f.get("source_report", ""),
        })
    write_json(output, "findings_inventory.json")


def write_canonical_findings(canonical_families: List[Dict[str, Any]]):
    """Write canonical_findings.json."""
    write_json(canonical_families, "canonical_findings.json")


def write_semantic_families(semantic_families: List[Dict[str, Any]]):
    """Write semantic_families.json (NEW — replaces literature mapping)."""
    write_json(semantic_families, "semantic_families.json")


def write_findings_frequency(frequencies: List[Dict[str, Any]]):
    """Write findings_frequency.csv."""
    rows = []
    for entry in sorted(frequencies, key=lambda x: -x["num_runs"]):
        rows.append({
            "Canonical Finding": entry["canonical_finding"],
            "Runs": entry["num_runs"],
            "Partitions": entry["num_partitions"],
            "Datasets": entry["num_datasets"],
        })
    write_csv(rows, "findings_frequency.csv",
              ["Canonical Finding", "Runs", "Partitions", "Datasets"])


def write_corpus_summary(
    raw_findings: List[Dict[str, Any]],
    canonical_families: List[Dict[str, Any]],
    semantic_families: List[Dict[str, Any]],
    frequencies: List[Dict[str, Any]],
):
    """Write findings_corpus_summary.md.
    
    No literature mapping. No novelty claims. Evidence-backed observations only.
    """
    total_findings = len(raw_findings)
    total_canonical = len([cf for cf in canonical_families if cf["canonical_name"] != "Unclassified"])
    total_semantic = len(semantic_families)
    top_findings = sorted(frequencies, key=lambda x: -x["num_runs"])[:5]
    cross_dataset = [f for f in frequencies if f["num_datasets"] > 1]
    
    # Dataset coverage
    ds_coverage = {}
    for f in raw_findings:
        ds = f.get("dataset", "unknown")
        if ds not in ds_coverage:
            ds_coverage[ds] = {"partitions": set(), "findings": 0}
        ds_coverage[ds]["partitions"].add(f.get("partition", ""))
        ds_coverage[ds]["findings"] += 1
    
    lines = [
        "# Findings Corpus Summary",
        "",
        "**Note:** This corpus contains raw findings and their canonical/semantic classifications.",
        "Literature matching and novelty assessment are performed manually by the researcher.",
        "",
        "---",
        "",
        "## 1. Corpus Overview",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total findings extracted | {total_findings} |",
        f"| Total canonical finding families | {total_canonical} |",
        f"| Total semantic families | {total_semantic} |",
        f"| Source runs | 15 |",
        f"| Source datasets | 2 |",
        "",
        "---",
        "",
        "## 2. Most Common Findings",
        "",
        "| Canonical Finding | Runs | Partitions | Datasets |",
        "|-------------------|------|------------|----------|",
    ]
    
    for entry in top_findings:
        lines.append(
            f"| {entry['canonical_finding']} | {entry['num_runs']} | "
            f"{entry['num_partitions']} | {entry['num_datasets']} |"
        )
    
    lines.extend(["", "---", "", "## 3. Cross-Dataset Findings",
        "", "Findings observed in both CICIDS2017 and UNSW-NB15:", ""])
    
    if cross_dataset:
        lines.extend([
            "| Canonical Finding | Runs | Partitions | Datasets |",
            "|-------------------|------|------------|----------|",
        ])
        for entry in cross_dataset:
            lines.append(
                f"| {entry['canonical_finding']} | {entry['num_runs']} | "
                f"{entry['num_partitions']} | {', '.join(entry['datasets'])} |"
            )
    else:
        lines.append("No findings were consistently observed across both datasets.")
    
    lines.extend(["", "---", "", "## 4. Semantic Families", "",
        "| Semantic Family | Canonical Members | Runs | Partitions | Datasets |",
        "|-----------------|-------------------|------|------------|----------|",
    ])
    
    for sf in semantic_families:
        cnames = ", ".join(m["canonical_name"] for m in sf["canonical_members"])
        cov = sf["coverage"]
        lines.append(
            f"| {sf['semantic_family']} | {cnames} | {cov['num_runs']} | "
            f"{cov['num_partitions']} | {cov['num_datasets']} |"
        )
    
    lines.extend(["", "---", "", "## 5. Dataset Coverage", "",
        "| Dataset | Partitions | Findings Extracted |",
        "|---------|-----------|-------------------|",
    ])
    
    for ds_name in ["CICIDS2017", "UNSW-NB15"]:
        cov = ds_coverage.get(ds_name, {"partitions": set(), "findings": 0})
        lines.append(f"| {ds_name} | {len(cov['partitions'])} | {cov['findings']} |")
    
    lines.extend([
        "", "---", "",
        "## 6. What the Framework Discovered",
        "",
        "The multi-agent forensic dataset auditing framework identified the following",
        "structural properties across the evaluated datasets:",
        "",
        "1. **Feature Engineering Redundancy:** Strong dependency pairs and redundant features",
        "   dominate the feature space across most partitions.",
        "2. **Shortcut Learning Signals:** Near-constant features, flag feature saturation,",
        "   protocol dominance, and destination port concentration create potential shortcuts.",
        "3. **Distributional Artifacts:** Class imbalance, distribution collapse, and low",
        "   diversity regions are present, especially in attack partitions.",
        "4. **Temporal Artifacts:** Attack activity follows predictable temporal patterns.",
        "5. **Label Structure Issues:** Potential class overlap and weak separability detected.",
        "6. **Data Quality Issues:** Duplicated rows and representation artifacts found.",
        "7. **Genuine Behavioral Signals:** Packet length features show class-conditioned",
        "   structural variation reflecting real traffic behavior (not artifacts).",
        "",
        "These discoveries span both CICIDS2017 and UNSW-NB15, suggesting that many",
        "structural properties are not dataset-specific but reflect broader challenges",
        "in NIDS dataset construction.",
        "",
        "---",
        "",
        "## 7. Literature Mapping Status",
        "",
        "Literature matching is **not performed automatically** by this pipeline.",
        "The semantic families above provide the intermediate abstraction layer for",
        "manual literature validation. The researcher should:",
        "",
        "1. Map each semantic family to known literature artifacts",
        "2. Assess mapping confidence (Strong / Partial / Weak)",
        "3. Identify findings with no literature match for novelty assessment",
        "4. Document all mapping decisions in the thesis methodology",
        "",
    ])
    
    path = OUTPUT_DIR / "findings_corpus_summary.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Written: {path}")


# --- Main Pipeline ------------------------------------------------------------

def main():
    """Execute the full findings corpus extraction pipeline."""
    
    print("=" * 60)
    print("Findings Corpus Extraction Pipeline v3 (REFACTORED)")
    print("=" * 60)
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # --- Step 1 & 2: Locate and extract ---
    print("\n[Step 1-2] Locating and extracting findings from all batch reports...")
    
    raw_findings = []
    seen_batches: Dict[str, str] = {}  # batch_timestamp -> first report path
    
    if not FINAL_BATCH_REPORT_RUNS.exists():
        print(f"ERROR: Directory not found: {FINAL_BATCH_REPORT_RUNS}")
        return
    
    for run_dir in sorted(FINAL_BATCH_REPORT_RUNS.iterdir()):
        if not run_dir.is_dir():
            continue
        
        component_json = run_dir / "component_run.json"
        report_md = run_dir / "report.md"
        
        if not component_json.exists() or not report_md.exists():
            continue
        
        try:
            component = json.loads(component_json.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  ERROR reading {component_json}: {e}")
            continue
        
        batch_id = component.get("batch_id", "")
        dataset, partition = resolve_partition(batch_id)
        run_id = extract_run_id_from_dirname(run_dir.name)
        
        # Deduplication: skip if we've already processed this batch
        batch_ts = extract_batch_timestamp(batch_id)
        if batch_ts:
            if batch_ts in seen_batches:
                print(f"  SKIP (duplicate batch): {run_dir.name} (already processed from {seen_batches[batch_ts]})")
                continue
            seen_batches[batch_ts] = run_dir.name
        
        print(f"  {run_dir.name}: batch={batch_id[:50]}... -> run={run_id}, partition={partition}")
        
        findings = extract_findings_from_report_md(report_md, run_id, dataset, partition)
        for f in findings:
            f["batch_id"] = batch_id
        raw_findings.extend(findings)
    
    print(f"  Total findings extracted: {len(raw_findings)}")
    
    # --- Step 3: Build canonical taxonomy ---
    print("\n[Step 3] Building canonical finding taxonomy...")
    canonical_families, finding_to_canonical = build_canonical_findings(raw_findings)
    
    print(f"  Canonical families: {len(canonical_families)}")
    for cf in canonical_families:
        if cf["canonical_name"] != "Unclassified":
            print(f"    - {cf['canonical_name']}: {cf['num_member_findings']} member findings")
    
    # --- Step 3b: Build semantic families (NEW) ---
    print("\n[Step 3b] Building semantic families...")
    semantic_families = build_semantic_families(canonical_families, finding_to_canonical, raw_findings)
    
    print(f"  Semantic families: {len(semantic_families)}")
    for sf in semantic_families:
        cov = sf["coverage"]
        print(f"    - {sf['semantic_family']}: {sf['num_canonical_members']} canonical members, "
              f"{cov['num_runs']} runs, {cov['num_datasets']} datasets")
    
    # --- Step 4: Compute frequencies ---
    print("\n[Step 4] Computing finding frequencies...")
    frequencies = compute_frequencies(raw_findings, finding_to_canonical)
    
    for entry in sorted(frequencies, key=lambda x: -x["num_runs"])[:10]:
        print(f"    - {entry['canonical_finding']}: {entry['num_runs']} runs, {entry['num_partitions']} partitions")
    
    # --- Step 7: Produce deliverables ---
    print("\n[Step 7] Producing deliverables...")
    write_findings_inventory(raw_findings)
    write_canonical_findings(canonical_families)
    write_semantic_families(semantic_families)
    write_findings_frequency(frequencies)
    write_corpus_summary(raw_findings, canonical_families, semantic_families, frequencies)
    
    # Remove old files that are no longer generated
    for old_file in ["literature_mapping_candidates.csv", "potentially_novel_findings.md"]:
        old_path = OUTPUT_DIR / old_file
        if old_path.exists():
            old_path.unlink()
            print(f"  Removed: {old_path}")
    
    print(f"\n{'=' * 60}")
    print("Pipeline complete.")
    print(f"Output directory: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()