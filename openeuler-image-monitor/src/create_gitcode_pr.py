import argparse
import json
import urllib.request
import urllib.error


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", required=True)
    parser.add_argument("--software", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--docker-tag", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--result-file", default="")
    args = parser.parse_args()

    title = f"\u3010\u81ea\u52a8\u6d4b\u8bd5\u3011{args.software}\u5bb9\u5668\u56fe\u50cf\u6027\u80fd\u57fa\u51c6\u6d4b\u8bd5 v{args.version}"

    body_lines = [
        f"# {args.software} v{args.version} \u6027\u80fd\u57fa\u51c6\u6d4b\u8bd5",
        "",
        "\u57fa\u4e8e ARM64 (Kunpeng-920, 32 cores) \u73af\u5668\u7684\u5bb9\u5668\u6027\u80fd\u57fa\u51c3\u6d4b\u8bd5\u7ed3\u679c\u3002",
        "",
        "## \u6d4b\u8bd5\u73af\u5668",
        "- \u67b6\u6784: aarch64",
        "- CPU: Kunpeng-920 (32 cores)",
        "- OS: openEuler 24.03 SP3",
        f"- Docker: openeuler/{args.software}:{args.docker_tag}",
        "",
        "## \u6d4b\u8bd5\u5185\u5bb9",
        "\u5305\u542b software-specific \u6027\u80fd\u57fa\u51c3\u6d4b\u8bd5\uff0c\u4f7f\u7528\u771f\u5b9e\u8ba1\u7b97\u4efb\u52a1\u6d4b\u91cf\u5bb9\u5668\u6027\u80fd\u3002",
        "",
    ]

    if args.result_file:
        try:
            with open(args.result_file) as f:
                result_lines = f.readlines()[:40]
            if result_lines:
                body_lines.append("## \u6d4b\u8bd5\u7ed3\u679c\u6458\u8981")
                body_lines.append("")
                body_lines.extend(line.rstrip() for line in result_lines)
                body_lines.append("")
        except Exception:
            pass

    body_lines.append("---")
    from datetime import datetime, timezone
    body_lines.append(f"\u81ea\u52a8\u751f\u6210\u4e8e {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")

    body = "\n".join(body_lines)

    data = {
        "access_token": args.token,
        "title": title,
        "body": body,
        "head": f"Tian-Fantasea:{args.branch}",
        "base": "master",
    }

    url = "https://gitcode.com/api/v5/repos/openeuler/openeuler-docker-images/pulls"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Private-Token": args.token,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if "id" in result:
                number = result.get("number", result.get("id"))
                html_url = result.get("html_url", result.get("web_url", ""))
                print(f"PR created successfully: #{number}")
                print(f"URL: {html_url}")
            else:
                print(f"PR creation response: {json.dumps(result)[:500]}")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"PR creation HTTP error {e.code}: {error_body[:500]}")
    except Exception as e:
        print(f"PR creation error: {e}")


if __name__ == "__main__":
    main()
