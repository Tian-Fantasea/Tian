import json
import sqlite3
import logging
import yaml
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.gitcode_client import GitCodeClient
from src.dockerhub_client import DockerHubClient
from src.docker_verifier import DockerVerifier
from src.test_generator import TestGenerator
from src.test_runner import TestRunner

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
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def save_verification(db_path: str, pr_number: int, software: str, tag: str,
                      verified: bool, image: str, digest: str, size: str, reason: str):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO docker_verification VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (pr_number, software, tag, int(verified), image, digest, size, reason,
         datetime.now(timezone.utc).isoformat()),
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

    since = (datetime.now(timezone.utc) - timedelta(hours=sch_cfg["lookback_hours"])).isoformat() + "Z"
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

    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    report_dir = Path(config_path).parent / "results" / timestamp
    report_dir.mkdir(parents=True, exist_ok=True)

    report_path = report_dir / "report.json"
    with open(report_path, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info(f"Report saved to {report_path}")

    txt_path = report_dir / "report.txt"
    generate_text_report(results, txt_path)
    logger.info(f"Text report saved to {txt_path}")

    tg_cfg = config.get("test_generation", {})
    if tg_cfg.get("enabled", False):
        tests_dir = tg_cfg.get("tests_dir", "../tests")
        tests_dir_path = Path(config_path).parent / tests_dir
        if not tests_dir_path.exists():
            logger.warning(f"Tests directory not found: {tests_dir_path}")
        else:
            reference_sw = tg_cfg.get("reference_software", "faiss")
            reference_dir = tests_dir_path / reference_sw / "scripts"
            docker_pull = tg_cfg.get("docker_pull", False)
            generator = TestGenerator(
                tests_dir=str(tests_dir_path),
                reference_dir=str(reference_dir) if reference_dir.exists() else "",
                docker_pull_enabled=docker_pull,
                ssh_host=v_cfg.get("ssh_host", ""),
                ssh_user=v_cfg.get("ssh_user", ""),
                ssh_port=v_cfg.get("ssh_port", 22),
                ssh_key_path=v_cfg.get("ssh_key_path", ""),
                docker_pull_timeout=v_cfg.get("docker_pull_timeout", 600),
            )
            pushed_results = [r for r in results if r["dockerhub_pushed"]]
            gen_results = generator.generate_for_pushed_images(
                pushed_results,
                namespace=dh_cfg["namespace"],
                docker_pull=docker_pull,
            )
            logger.info(f"Test scaffolding generated for {len([g for g in gen_results if g.get('status') == 'generated'])} new software")

            gen_report_path = report_dir / "test_generation.json"
            with open(gen_report_path, "w") as f:
                json.dump(gen_results, f, ensure_ascii=False, indent=2)
            logger.info(f"Test generation report saved to {gen_report_path}")

            txt_report_path = report_dir / "test_generation.txt"
            generate_test_generation_report(gen_results, txt_report_path)
            logger.info(f"Test generation text report saved to {txt_report_path}")

    tr_cfg = config.get("test_runner", {})
    if tr_cfg.get("enabled", False):
        tests_dir = tg_cfg.get("tests_dir", "../tests") if tg_cfg.get("enabled", False) else "../tests"
        tests_dir_path = Path(config_path).parent / tests_dir
        if not tests_dir_path.exists():
            logger.warning(f"Tests directory not found: {tests_dir_path}, cannot run tests")
        else:
            runner = TestRunner(
                tests_dir=str(tests_dir_path),
                timeout=tr_cfg.get("timeout", 3600),
            )
            pushed_results = [r for r in results if r["dockerhub_pushed"]]
            software_list = [
                {"software": r["software"], "version": r["version"]}
                for r in pushed_results if r["software"]
            ]
            run_results = runner.run_all(software_list)
            logger.info(f"Test execution completed: {len([r for r in run_results if r.get('status') == 'completed'])} completed")

            run_report_path = report_dir / "test_execution.json"
            with open(run_report_path, "w") as f:
                json.dump(run_results, f, ensure_ascii=False, indent=2)
            logger.info(f"Test execution report saved to {run_report_path}")

            txt_exec_path = report_dir / "test_execution.txt"
            generate_test_execution_report(run_results, txt_exec_path)
            logger.info(f"Test execution text report saved to {txt_exec_path}")

    return results


def generate_text_report(results: list, txt_path: Path):
    pushed = [r for r in results if r["dockerhub_pushed"]]
    not_pushed = [r for r in results if not r["dockerhub_pushed"]]
    total = len(results)

    lines = []
    lines.append("=" * 80)
    lines.append(f"openEuler Docker Image Monitor Report")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
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
        lines.append("  (none)")

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


def generate_test_generation_report(gen_results: list, txt_path: Path):
    generated = [g for g in gen_results if g.get("status") == "generated"]
    existing = [g for g in gen_results if g.get("status") == "existing"]
    total = len(gen_results)

    lines = []
    lines.append("=" * 80)
    lines.append("  Test Scaffolding Generation Report")
    lines.append(f"  Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"  Total: {total}  |  New: {len(generated)}  |  Existing: {len(existing)}")
    lines.append("=" * 80)

    lines.append("")
    lines.append("=" * 80)
    lines.append(f"  NEWLY GENERATED ({len(generated)} software)")
    lines.append("=" * 80)
    if generated:
        lines.append(f"  {'Software':<22} {'Version':<18} {'Benchmark':<18} {'Build':<16} {'Docker':<16}")
        lines.append(f"  {'--------':<22} {'-------':<18} {'---------':<18} {'-----':<16} {'-----':<16}")
        for g in generated:
            sw = g.get("software", "-")
            ver = g.get("version", "-")
            bm = g.get("benchmark_type", "-")
            build = g.get("build_method", "-")
            docker = g.get("docker_status", "-")
            lines.append(f"  {sw:<22} {ver:<18} {bm:<18} {build:<16} {docker:<16}")
        lines.append("")
        for g in generated:
            lines.append(f"  {g.get('software','-')} files:")
            for f_name in g.get("files", []):
                lines.append(f"    - {f_name}")
            lines.append("")
    else:
        lines.append("  (none - all software already have tests)")

    lines.append("")
    lines.append("=" * 80)
    lines.append(f"  ALREADY EXISTING ({len(existing)} software)")
    lines.append("=" * 80)
    if existing:
        for g in existing:
            lines.append(f"  {g.get('software','-')}: {g.get('message','-')}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("=" * 80)

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def generate_test_execution_report(run_results: list, txt_path: Path):
    completed = [r for r in run_results if r.get("status") == "completed"]
    partial = [r for r in run_results if r.get("status", "").startswith("partial")]
    failed = [r for r in run_results if r.get("status") in ("timeout", "error", "script_not_found")]
    skipped = [r for r in run_results if r.get("status") == "already_completed"]
    scaffold = [r for r in run_results if r.get("status") == "scaffold_skipped"]
    total = len(run_results)

    lines = []
    lines.append("=" * 80)
    lines.append("  Test Execution Report")
    lines.append(f"  Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"  Total: {total}  |  Completed: {len(completed)}  |  Partial: {len(partial)}  |  Failed: {len(failed)}  |  Skipped: {len(skipped)}  |  Scaffold: {len(scaffold)}")
    lines.append("=" * 80)

    lines.append("")
    lines.append("=" * 80)
    lines.append(f"  COMPLETED ({len(completed)} software)")
    lines.append("=" * 80)
    if completed:
        lines.append(f"  {'Software':<22} {'Version':<18} {'Time(s)':<12} {'ReturnCode':<12}")
        lines.append(f"  {'--------':<22} {'-------':<18} {'------':<12} {'---------':<12}")
        for r in completed:
            sw = r.get("software", "-")
            ver = r.get("version", "-")
            elapsed = r.get("elapsed_seconds", "-")
            rc = r.get("returncode", "-")
            lines.append(f"  {sw:<22} {ver:<18} {elapsed:<12} {rc:<12}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("=" * 80)
    lines.append(f"  PARTIAL ({len(partial)} software)")
    lines.append("=" * 80)
    if partial:
        for r in partial:
            lines.append(f"  {r.get('software','-')} v{r.get('version','-')}: {r.get('status','-')}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("=" * 80)
    lines.append(f"  FAILED ({len(failed)} software)")
    lines.append("=" * 80)
    if failed:
        lines.append(f"  {'Software':<22} {'Version':<18} {'Status':<16} {'Detail'}")
        lines.append(f"  {'--------':<22} {'-------':<18} {'-----':<16} {'-----'}")
        for r in failed:
            sw = r.get("software", "-")
            ver = r.get("version", "-")
            st = r.get("status", "-")
            detail = r.get("error", r.get("stderr_tail", "-"))[:40]
            lines.append(f"  {sw:<22} {ver:<18} {st:<16} {detail}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("=" * 80)
    lines.append(f"  SKIPPED (already had results) ({len(skipped)} software)")
    lines.append("=" * 80)
    if skipped:
        for r in skipped:
            lines.append(f"  {r.get('software','-')} v{r.get('version','-')}: {r.get('message','-')}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("=" * 80)
    lines.append(f"  SCAFFOLD (needs manual implementation) ({len(scaffold)} software)")
    lines.append("=" * 80)
    if scaffold:
        for r in scaffold:
            lines.append(f"  {r.get('software','-')} v{r.get('version','-')}: {r.get('message','-')}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("=" * 80)
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
