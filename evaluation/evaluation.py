"""
AppForge Evaluation Framework
Runs 10 real product prompts + 10 edge cases and tracks metrics.
"""

import os
import json
import time
import statistics
from pipeline import AppForgePipeline
from dotenv import load_dotenv

load_dotenv()

REAL_PROMPTS = [
    "Build a CRM with login, contacts dashboard, role-based access for admin and sales, and premium plan with Stripe payments. Admins can see analytics.",
    "Create an e-commerce platform with product catalog, shopping cart, checkout with payments, order tracking, and admin panel for inventory management.",
    "Build a project management tool like Trello with boards, cards, drag-and-drop, team collaboration, deadlines, and Slack notifications.",
    "Create a SaaS analytics dashboard that tracks user events, shows charts, has team workspaces, billing, and API access for developers.",
    "Build a healthcare appointment booking system with patient profiles, doctor schedules, video calls, prescriptions, and insurance billing.",
    "Create a food delivery app with restaurant listings, menu management, real-time order tracking, driver assignment, and ratings.",
    "Build an online learning platform with courses, video lessons, quizzes, progress tracking, certificates, and instructor payouts.",
    "Create a real estate listing platform with property search, virtual tours, agent profiles, mortgage calculator, and lead management.",
    "Build a social media scheduling tool with multi-platform posting, analytics, team collaboration, approval workflows, and AI caption generation.",
    "Create a HR management system with employee onboarding, leave management, performance reviews, payroll integration, and org chart."
]

EDGE_CASES = [
    # Vague
    "Build an app",
    "I want something for my business",
    # Conflicting
    "Build a free app with no login but also with premium features and user data privacy. Make it both public and private.",
    "Create an app where all users are admins but also have no permissions and can only view content.",
    # Incomplete
    "Build a marketplace",
    "Create something with payments and users",
    # Over-specified contradictions
    "Build a social network with 500 features including blockchain NFT integration, AR/VR support, AI chatbot, quantum encryption, and real-time translation for 200 languages, all for free with no backend.",
    # Missing core info
    "App for doctors",
    # Ambiguous roles
    "Build a platform where users can be both buyers and sellers and also moderators and admins at the same time with different dashboards.",
    # Pure jargon
    "B2B SaaS multi-tenant microservices event-driven CQRS platform with eventual consistency and distributed transactions."
]


def run_evaluation():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set in .env")

    pipeline = AppForgePipeline(api_key=api_key)
    results = []

    all_prompts = [("real", p) for p in REAL_PROMPTS] + [("edge", p) for p in EDGE_CASES]

    print(f"\n{'='*60}")
    print("AppForge Evaluation Framework")
    print(f"Running {len(all_prompts)} test cases...")
    print(f"{'='*60}\n")

    for i, (ptype, prompt) in enumerate(all_prompts, 1):
        print(f"[{i:02d}/{len(all_prompts)}] [{ptype.upper()}] {prompt[:60]}...")
        t_start = time.time()
        try:
            result = pipeline.run(prompt)
            elapsed = time.time() - t_start
            status = result.get("status", "unknown")
            metrics = result.get("metrics", {})
            validation = result.get("validation", {})
            exec_report = result.get("execution_report", {})

            record = {
                "id": i,
                "type": ptype,
                "prompt": prompt[:80],
                "status": status,
                "latency_s": round(elapsed, 2),
                "retries": metrics.get("retries", 0),
                "repairs": metrics.get("repair_count", 0),
                "tokens": metrics.get("tokens_used", 0),
                "is_valid": validation.get("is_valid", False),
                "errors": len(validation.get("errors", [])),
                "warnings": len(validation.get("warnings", [])),
                "executable": exec_report.get("status") == "executable",
                "db_tables": exec_report.get("db_tables_count", 0),
                "assumptions": metrics.get("assumptions", [])
            }
            results.append(record)
            print(f"     ✓ Status={status} Valid={record['is_valid']} Executable={record['executable']} Time={elapsed:.1f}s Tokens={record['tokens']}")
        except Exception as e:
            elapsed = time.time() - t_start
            results.append({
                "id": i, "type": ptype, "prompt": prompt[:80],
                "status": "error", "latency_s": round(elapsed, 2),
                "error": str(e)[:100], "is_valid": False, "executable": False,
                "retries": 0, "repairs": 0, "tokens": 0, "errors": 1, "warnings": 0, "db_tables": 0
            })
            print(f"     ✗ ERROR: {e}")

        time.sleep(0.5)  # Rate limit buffer

    # ── Compute aggregate metrics ──
    real_results = [r for r in results if r["type"] == "real"]
    edge_results = [r for r in results if r["type"] == "edge"]

    def rate(lst, key):
        return round(sum(1 for r in lst if r.get(key)) / len(lst) * 100, 1) if lst else 0

    summary = {
        "total_cases": len(results),
        "real_prompts": {
            "count": len(real_results),
            "success_rate_pct": rate(real_results, "is_valid"),
            "executable_rate_pct": rate(real_results, "executable"),
            "avg_latency_s": round(statistics.mean(r["latency_s"] for r in real_results), 2),
            "avg_tokens": round(statistics.mean(r.get("tokens", 0) for r in real_results), 0),
            "avg_retries": round(statistics.mean(r.get("retries", 0) for r in real_results), 2),
            "avg_repairs": round(statistics.mean(r.get("repairs", 0) for r in real_results), 2),
        },
        "edge_cases": {
            "count": len(edge_results),
            "handled_gracefully_pct": rate(edge_results, "status"),  # any non-crash
            "clarification_asked_pct": rate(edge_results, "is_valid"),
        },
        "overall": {
            "success_rate_pct": rate(results, "is_valid"),
            "executable_rate_pct": rate(results, "executable"),
            "total_tokens": sum(r.get("tokens", 0) for r in results),
            "avg_latency_s": round(statistics.mean(r["latency_s"] for r in results), 2),
        }
    }

    # Print report
    print(f"\n{'='*60}")
    print("EVALUATION RESULTS")
    print(f"{'='*60}")
    print(json.dumps(summary, indent=2))

    # Save results
    output = {"summary": summary, "detailed_results": results}
    with open("evaluation_results.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Full results saved to evaluation_results.json")
    return output


if __name__ == "__main__":
    run_evaluation()