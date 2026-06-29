import json
import sqlite3
import logging
import yaml
from datetime import datetime, timedelta
from pathlib import Path

from src.gitcode_client import GitCodeClient
from src.dockerhub_client import DockerHubClient
from src.docker_verifier import DockerVerifier

logger = logging.getLogger(__name__)


def load_config(config_path: str) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def init_db(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pr_tracking (
            pr_number INTEGER PRIMARY KEY,
            merged_at TEXT,
            software TEXT,
            version TEXT,
            os_version TEXT,
            category TEXT,
            filepath TEXT,
            title TEXT,
            source TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dockerhub_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pr_number INTEGER,
            software TEXT,
            version TEXT,
            os_version TEXT,
            pushed INTEGER,
            tag TEXT,
            reason TEXT,
            checked_at TEXT,
            FOREIGN KEY (pr_number) REFERENCES pr_tracking(pr_number)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS docker_verification (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pr_number INTEGER,
            software TEXT,
            tag TEXT,
            verified INTEGER,
            image TEXT,
            digest TEXT,
            size TEXT,
            reason TEXT,
            verified_at TEXT,
            FOREIGN KEY (pr_number) REFERENCES pr_tracking(pr_number)
        )
    """)
    conn.commit()
    conn.close()


def is_pr_processed(db_path: str, pr_number: int) -> bool:
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT 1 FROM pr_tracking WHERE pr_number = ?", (pr_number,)
    ).fetchone()
    conn.close()
    return row is not None


def save_pr_info(db_path: str, pr_number: int, merged_at: str, software: str,
                 version: str, os_version: str, category: str, filepath: str,
                 title: str, source: str):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR REPLACE INTO pr_tracking VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (pr_number, merged_at, software, version, os_version, category, filepath, title, source),
    )
    conn.commit()
    conn.close()


def save_dockerhub_status(db_path: str, pr_number: int, software: str, version: str,
                          os_version: str, pushed: bool, tag: str, reason: str):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO dockerhub_status VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
        (pr_number, software, version, os_version, int(pushed), tag, reason,
         datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def save_verification(db_path: str, pr_number: int, software: str, tag: str,
                      verified: bool, image: str, digest: str, size: str, reason: str):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO docker_verification VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (pr_number, software, tag, int(verified), image, digest, size, reason,
         datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def run_pipeline(config_path: str):
    config = load_config(config_path)
    db_path = config["state"]["db_path"]
    init_db(db_path)

    gc_cfg = config["gitcode"]
    dh_cfg = config["dockerhub"]
    v_cfg = config["verification"]
    sch_cfg = config["schedule"]

    gitcode = GitCodeClient(
        gc_cfg["base_url"], gc_cfg["repo_owner"], gc_cfg["repo_name"], gc_cfg.get("access_token", "")
    )
    dockerhub = DockerHubClient(dh_cfg["base_url"], dh_cfg["namespace"])
    verifier = DockerVerifier(
        enabled=v_cfg["enabled"],
        ssh_host=v_cfg.get("ssh_host", ""),
        ssh_user=v_cfg.get("ssh_user", ""),
        ssh_port=v_cfg.get("ssh_port", 22),
        ssh_key_path=v_cfg.get("ssh_key_path", ""),
        docker_pull_timeout=v_cfg.get("docker_pull_timeout", 600),
    )

    since = (datetime.utcnow() - timedelta(hours=sch_cfg["lookback_hours"])).isoformat() + "Z"
    logger.info(f"Fetching merged PRs since {since}")

    prs = gitcode.get_merged_prs_since(since)
    logger.info(f"Found {len(prs)} merged PRs since {since}")

    results = []

    for pr in prs:
        pr_number = pr["number"]
        merged_at = pr.get("merged_at", "")
        title = pr.get("title", "")

        if is_pr_processed(db_path, pr_number):
            logger.info(f"PR #{pr_number} already processed, skipping")
            continue

        logger.info(f"Processing PR #{pr_number}: {title}")

        software_infos = gitcode.extract_software_info_from_files(pr_number)
        if not software_infos:
            logger.warning(f"PR #{pr_number}: could not extract software info")
            continue

        for info in software_infos:
            software = info.get("software", "")
            version = info.get("version", "")
            os_version = info.get("os_version", "")
            category = info.get("category", "")
            filepath = info.get("filepath", "")
            source = info.get("source", "filepath")

            if not software:
                logger.warning(f"PR #{pr_number}: empty software name, skipping")
                continue

            save_pr_info(db_path, pr_number, merged_at, software, version, os_version,
                         category, filepath, title, source)

            dh_status = dockerhub.check_image_pushed(software, version, os_version)
            save_dockerhub_status(
                db_path, pr_number, software, version, os_version,
                dh_status["pushed"], dh_status.get("tag", ""), dh_status.get("reason", ""),
            )

            verification = {"verified": False, "reason": "image_not_pushed"}
            if dh_status["pushed"]:
                tag = dh_status.get("tag", "latest")
                if verifier.enabled:
                    verification = verifier.verify_pull(
                        dh_cfg["namespace"], software, tag
                    )
                else:
                    verification = {
                        "verified": False,
                        "reason": "verification_disabled",
                        "software": software,
                        "tag": tag,
                    }

            save_verification(
                db_path, pr_number, software, dh_status.get("tag", ""),
                verification.get("verified", False),
                verification.get("image", ""),
                verification.get("digest", ""),
                verification.get("size", ""),
                verification.get("reason", ""),
            )

            result = {
                "pr_number": pr_number,
                "merged_at": merged_at,
                "title": title,
                "software": software,
                "version": version,
                "os_version": os_version,
                "category": category,
                "filepath": filepath,
                "dockerhub_pushed": dh_status["pushed"],
                "dockerhub_tag": dh_status.get("tag", ""),
                "dockerhub_reason": dh_status.get("reason", ""),
                "docker_verified": verification.get("verified", False),
                "verification_reason": verification.get("reason", ""),
            }
            results.append(result)
            logger.info(
                f"PR #{pr_number} {software}/{version}/{os_version}: "
                f"DH pushed={dh_status['pushed']} tag={dh_status.get('tag','')} "
                f"verified={verification.get('verified', False)}"
            )

    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    report_dir = Path(config_path).parent

    report_path = report_dir / f"report_{timestamp}.json"
    with open(report_path, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info(f"Report saved to {report_path}")

    txt_path = report_dir / f"report_{timestamp}.txt"
    generate_text_report(results, txt_path)
    logger.info(f"Text report saved to {txt_path}")

    return results


def generate_text_report(results: list, txt_path: Path):
    pushed = [r for r in results if r["dockerhub_pushed"]]
    not_pushed = [r for r in results if not r["dockerhub_pushed"]]
    total = len(results)

    lines = []
    lines.append("=" * 80)
    lines.append(f"openEuler Docker Image Monitor Report")
    lines.append(f"Generated: {datetime.utcnow().isoformat()}")
    lines.append(f"Total PRs: {total}  |  Pushed: {len(pushed)}  |  Not Pushed: {len(not_pushed)}")
    lines.append("=" * 80)

    lines.append("")
    lines.append("=" * 80)
    lines.append(f"  DockerHub ALREADY PUSHED ({len(pushed)} images)")
    lines.append("=" * 80)
    if pushed:
        lines.append(f"  {'PR#':<8} {'Software':<22} {'Version':<18} {'OS':<18} {'Tag':<28}")
        lines.append(f"  {'----':<8} {'--------':<22} {'-------':<18} {'--':<18} {'---':<28}")
        for r in pushed:
            sw = r["software"] or "-"
            ver = r["version"] or "-"
            osv = r["os_version"] or "-"
            tag = r["dockerhub_tag"] or "-"
            lines.append(f"  {r['pr_number']:<8} {sw:<22} {ver:<18} {osv:<18} {tag:<28}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("=" * 80)
    lines.append(f"  DockerHub NOT PUSHED ({len(not_pushed)} images)")
    lines.append("=" * 80)
    if not_pushed:
        lines.append(f"  {'PR#':<8} {'Software':<22} {'Version':<18} {'Reason':<30} {'Title'}")
        lines.append(f"  {'----':<8} {'--------':<22} {'-------':<18} {'------':<30} {'-----'}")
        for r in not_pushed:
            sw = r["software"] or "-"
            ver = r["version"] or "-"
            reason = r["dockerhub_reason"] or "-"
            title = r["title"][:50] if r["title"] else "-"
            lines.append(f"  {r['pr_number']:<8} {sw:<22} {ver:<18} {reason:<30} {title}")
    else:
        lines.append("  (none - all images are pushed!)")

    lines.append("")
    lines.append("=" * 80)
    lines.append("  Summary by Category")
    lines.append("=" * 80)
    cats = {}
    for r in results:
        cat = r.get("category", "") or "Unknown"
        cats[cat] = cats.get(cat, 0) + 1
    for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
        lines.append(f"  {cat:<20} {cnt}")

    lines.append("")
    lines.append("=" * 80)
    lines.append("  Tag Match Statistics")
    lines.append("=" * 80)
    exact_tag = len([r for r in pushed if r["dockerhub_tag"] and r["dockerhub_tag"] != "latest"])
    latest_only = len([r for r in pushed if r["dockerhub_tag"] == "latest"])
    no_tag_info = len([r for r in pushed if not r["dockerhub_tag"]])
    lines.append(f"  Exact version tag (e.g. 7.22-oe2403sp3):  {exact_tag}")
    lines.append(f"  Only 'latest' tag:                          {latest_only}")
    lines.append(f"  No tag info:                                 {no_tag_info}")

    lines.append("")
    lines.append("=" * 80)

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    import argparse
    parser = argparse.ArgumentParser(description="openEuler Docker Image Monitor")
    parser.add_argument("-c", "--config", default="config.yaml", help="Config file path")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    run_pipeline(args.config)


if __name__ == "__main__":
    main()
