"""Contracts and constants for the Phase 3 Final Partition Audit Report Generator."""

from __future__ import annotations

SCHEMA_VERSION = "phase3.final_batch_report.v1"
PROMPT_VERSION = "phase3.final_batch_report.prompt.v1"

CICIDS2017_PARTITION_SCENARIOS: dict[str, str] = {
    "ddos": (
        "This partition models a DDoS (Distributed Denial of Service) scenario "
        "in which attack traffic is expected to target a limited service surface. "
        "Expected characteristics include: "
        "strong concentration patterns, "
        "repetitive flow structures, "
        "skewed feature distributions, "
        "and high traffic volume concentration. "
        "Unexpected structural artifacts may indicate: "
        "dataset construction issues, "
        "feature engineering artifacts, "
        "shortcut opportunities, "
        "or labeling inconsistencies."
    ),
    "portscan": (
        "This partition models a PortScan scenario in which reconnaissance traffic "
        "systematically probes multiple ports and hosts. "
        "Expected characteristics include: "
        "widespread connection attempts across many destinations, "
        "high protocol diversity, "
        "and distinctive temporal scanning patterns. "
        "Unexpected structural artifacts may indicate: "
        "dataset construction issues, "
        "feature engineering artifacts, "
        "shortcut opportunities, "
        "or labeling inconsistencies."
    ),
    "web": (
        "This partition models Web Attack scenarios including XSS and SQL injection. "
        "Expected characteristics include: "
        "HTTP-level pattern concentration, "
        "specific payload structure repetition, "
        "and application-layer behavioral signatures. "
        "Unexpected structural artifacts may indicate: "
        "dataset construction issues, "
        "feature engineering artifacts, "
        "shortcut opportunities, "
        "or labeling inconsistencies."
    ),
    "infiltration": (
        "This partition models an Infiltration scenario where an attacker "
        "gradually compromises internal network resources. "
        "Expected characteristics include: "
        "low-and-slow traffic patterns, "
        "internal lateral movement signatures, "
        "and blended benign-malicious sequences. "
        "Unexpected structural artifacts may indicate: "
        "dataset construction issues, "
        "feature engineering artifacts, "
        "shortcut opportunities, "
        "or labeling inconsistencies."
    ),
    "bruteforce": (
        "This partition models Brute Force authentication attacks (FTP/SSH). "
        "Expected characteristics include: "
        "repeated authentication failure patterns, "
        "high connection attempt rates, "
        "and distinctive credential-guessing signatures. "
        "Unexpected structural artifacts may indicate: "
        "dataset construction issues, "
        "feature engineering artifacts, "
        "shortcut opportunities, "
        "or labeling inconsistencies."
    ),
    "benign": (
        "This partition models Benign (normal) network traffic. "
        "Expected characteristics include: "
        "diverse traffic patterns, "
        "no dominant attack signatures, "
        "natural protocol and destination variety, "
        "and typical business-hour usage profiles. "
        "Unexpected structural artifacts may indicate: "
        "dataset construction issues, "
        "feature engineering artifacts, "
        "shortcut opportunities, "
        "or labeling inconsistencies."
    ),
}