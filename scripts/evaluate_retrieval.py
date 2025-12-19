"""
NORTH AI - Retrieval Quality Evaluation Script

This script evaluates the quality of NORTH's multi-agent orchestration system by:
1. Testing agent routing accuracy (does the right agent handle the query?)
2. Measuring response quality (does it contain expected entities?)
3. Tracking performance metrics (latency, estimated token usage)
4. Generating a summary report

Usage:
    python scripts/evaluate_retrieval.py
    python scripts/evaluate_retrieval.py --verbose  # Show full responses
"""

import os
import sys
import time
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
from statistics import mean, median

# Fix Windows console encoding for Unicode
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from src.core.north_orchestrator import NORTH

# Load environment
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.WARNING,  # Suppress info logs during evaluation
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class TestCase:
    """Represents a single evaluation test case"""
    query: str
    expected_agent: str  # 'obsidian', 'dropbox', 'both', or 'conversational'
    expected_entities: List[str]  # Must appear in response
    category: str  # Type of query (contractor_lookup, document_search, etc.)
    description: str  # Human-readable description


@dataclass
class EvaluationResult:
    """Results for a single test case"""
    query: str
    expected_agent: str
    detected_agent: str
    agent_correct: bool
    entities_found: List[str]
    entities_missing: List[str]
    entity_recall: float  # Percentage of expected entities found
    latency_ms: float
    response_length: int
    estimated_tokens: int
    response_preview: str  # First 100 chars
    full_response: str  # Complete response for detailed analysis


# ==================== TEST CASES ====================

TEST_CASES = [
    # === OBSIDIAN KNOWLEDGE BASE QUERIES ===
    TestCase(
        query="Who did electrical work on 305 Regency?",
        expected_agent="obsidian",
        expected_entities=["Triple Eagle Electric", "electrical", "Regency"],
        category="contractor_lookup",
        description="Find contractor by service type and project"
    ),
    TestCase(
        query="What's the phone number for Triple Eagle Electric?",
        expected_agent="obsidian",
        expected_entities=["Triple Eagle", "phone", "555", "contact"],
        category="contact_info",
        description="Retrieve contractor contact information"
    ),
    TestCase(
        query="Who are all the plumbing contractors we've worked with?",
        expected_agent="obsidian",
        expected_entities=["plumb", "contractor"],
        category="service_filter",
        description="List contractors by service type"
    ),
    TestCase(
        query="List companies tagged as electrician",
        expected_agent="obsidian",
        expected_entities=["electric"],
        category="service_filter",
        description="Query by service tag"
    ),
    TestCase(
        query="What projects has ABC Electric worked on?",
        expected_agent="obsidian",
        expected_entities=["project", "ABC"],
        category="project_history",
        description="Find project history for contractor"
    ),

    # === DROPBOX DOCUMENT SEARCH QUERIES ===
    TestCase(
        query="Find the signed contract with Triple Eagle Electric",
        expected_agent="dropbox",
        expected_entities=["Triple Eagle", "contract", "sign"],
        category="document_search",
        description="Locate specific contract document"
    ),
    TestCase(
        query="Show me W9 forms for 305 Regency contractors",
        expected_agent="dropbox",
        expected_entities=["W9", "305 Regency"],
        category="document_search",
        description="Find tax documents by project"
    ),
    TestCase(
        query="Find insurance documents for All Around Texas Plumbing",
        expected_agent="dropbox",
        expected_entities=["insurance", "All Around Texas", "COI"],
        category="document_search",
        description="Locate insurance certificates"
    ),
    TestCase(
        query="List all invoices for Porter & Bier",
        expected_agent="dropbox",
        expected_entities=["invoice", "Porter", "Bier"],
        category="document_search",
        description="Find invoices by contractor name"
    ),

    # === MULTI-SOURCE QUERIES (Both agents) ===
    TestCase(
        query="Tell me about Triple Eagle Electric and show their contract",
        expected_agent="both",
        expected_entities=["Triple Eagle", "contract"],
        category="multi_source",
        description="Combine knowledge base info with document retrieval"
    ),
    TestCase(
        query="Who did plumbing on 305 Regency and where are their documents?",
        expected_agent="both",
        expected_entities=["plumb", "305 Regency", "document"],
        category="multi_source",
        description="Contractor lookup + document location"
    ),

    # === CONVERSATIONAL QUERIES ===
    TestCase(
        query="Hello, can you help me?",
        expected_agent="conversational",
        expected_entities=["help", "NORTH"],
        category="greeting",
        description="General greeting/introduction"
    ),
    TestCase(
        query="What can you do?",
        expected_agent="conversational",
        expected_entities=["knowledge", "search", "contractor", "document"],
        category="capability_inquiry",
        description="Explain NORTH's capabilities"
    ),
]


# ==================== EVALUATION LOGIC ====================

class NORTHEvaluator:
    """Evaluates NORTH's retrieval and orchestration quality"""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.north = None
        self.results: List[EvaluationResult] = []

        # Cost estimation (approximate GPT-4o pricing)
        self.cost_per_1k_tokens = 0.005  # $5 per 1M tokens = $0.005 per 1K

    def initialize(self):
        """Initialize NORTH instance"""
        print("🚀 Initializing NORTH AI System...")
        try:
            self.north = NORTH()
            print(f"✅ NORTH initialized with {len(self.north.agents)} agents")

            # Show available agents
            if self.north.agents:
                print(f"   Available agents: {', '.join(self.north.agents.keys())}")
            else:
                print("   ⚠️  Warning: No agents initialized")
                print("   Make sure Weaviate is running: docker start weaviate_north")

        except Exception as e:
            print(f"❌ Failed to initialize NORTH: {e}")
            raise

    def _map_tools_to_agent(self, tools_used: List[str]) -> str:
        """
        Map tool names to agent types using GROUND TRUTH from LangChain.
        This replaces brittle string heuristics with actual tool invocation data.

        Args:
            tools_used: List of tool names actually invoked (from AgentExecutor)

        Returns:
            Agent type: 'obsidian', 'dropbox', 'both', 'conversational', or 'unknown'
        """
        if not tools_used:
            return "conversational"  # No tools used = direct LLM response

        # Tool name → Agent mapping
        obsidian_tools = {"search_knowledge_base"}
        dropbox_tools = {"search_dropbox_files"}

        # Check which agents were actually used
        obsidian_used = any(tool in obsidian_tools for tool in tools_used)
        dropbox_used = any(tool in dropbox_tools for tool in tools_used)

        if obsidian_used and dropbox_used:
            return "both"
        elif obsidian_used:
            return "obsidian"
        elif dropbox_used:
            return "dropbox"
        else:
            # Unknown tool was used (shouldn't happen normally)
            return "unknown"

    def _detect_agent_used_legacy(self, response: str) -> str:
        """
        DEPRECATED: Heuristic-based agent detection (kept for backwards compatibility).
        Use _map_tools_to_agent with actual tool usage data instead.
        """
        response_lower = response.lower()

        # Check for tool usage indicators
        obsidian_indicators = [
            "knowledge base",
            "obsidian",
            "notes show",
            "according to my records",
            "in my database"
        ]

        dropbox_indicators = [
            "dropbox",
            "document",
            "file",
            ".pdf",
            "contract",
            "invoice",
            "w9",
            "insurance",
            "found in"
        ]

        obsidian_used = any(indicator in response_lower for indicator in obsidian_indicators)
        dropbox_used = any(indicator in response_lower for indicator in dropbox_indicators)

        if obsidian_used and dropbox_used:
            return "both"
        elif obsidian_used:
            return "obsidian"
        elif dropbox_used:
            return "dropbox"
        else:
            # Check if it's a conversational response (no tool usage)
            if len(response) < 200 and ("help" in response_lower or "can" in response_lower):
                return "conversational"
            return "unknown"

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (rough approximation: 1 token ≈ 4 chars)"""
        return len(text) // 4

    def _check_entities(self, response: str, expected_entities: List[str]) -> tuple[List[str], List[str]]:
        """Check which expected entities are present in response"""
        response_lower = response.lower()
        found = []
        missing = []

        for entity in expected_entities:
            if entity.lower() in response_lower:
                found.append(entity)
            else:
                missing.append(entity)

        return found, missing

    def run_test_case(self, test: TestCase) -> EvaluationResult:
        """Execute a single test case and measure results using GROUND TRUTH routing data"""

        # Clear context before each test for isolation
        self.north.context_manager.clear()

        # Use process_query_with_metadata to get ground-truth tool usage
        result = self.north.process_query_with_metadata(test.query)

        # Extract data from metadata
        response = result["response"]
        tools_used = result["tools_used"]
        latency_ms = result["latency_ms"]

        # Map actual tools used to agent type (GROUND TRUTH - no heuristics!)
        detected_agent = self._map_tools_to_agent(tools_used)

        # Check if agent routing was correct
        agent_correct = (
            detected_agent == test.expected_agent or
            (test.expected_agent == "both" and detected_agent in ["obsidian", "dropbox", "both"])
        )

        # Check entity presence
        entities_found, entities_missing = self._check_entities(response, test.expected_entities)
        entity_recall = len(entities_found) / len(test.expected_entities) if test.expected_entities else 1.0

        # Estimate tokens
        estimated_tokens = self._estimate_tokens(response)

        # Create preview
        response_preview = response[:100] + "..." if len(response) > 100 else response

        return EvaluationResult(
            query=test.query,
            expected_agent=test.expected_agent,
            detected_agent=detected_agent,
            agent_correct=agent_correct,
            entities_found=entities_found,
            entities_missing=entities_missing,
            entity_recall=entity_recall,
            latency_ms=latency_ms,
            response_length=len(response),
            estimated_tokens=estimated_tokens,
            response_preview=response_preview,
            full_response=response
        )

    def run_all_tests(self):
        """Run all test cases and collect results"""
        print(f"\n📋 Running {len(TEST_CASES)} evaluation tests...\n")

        for i, test in enumerate(TEST_CASES, 1):
            print(f"[{i}/{len(TEST_CASES)}] {test.category}: {test.description}")
            print(f"   Query: \"{test.query}\"")

            try:
                result = self.run_test_case(test)
                self.results.append(result)

                # Show immediate feedback
                status = "✅" if result.agent_correct and result.entity_recall >= 0.5 else "⚠️"
                print(f"   {status} Agent: {result.detected_agent} | Entities: {len(result.entities_found)}/{len(test.expected_entities)} | {result.latency_ms:.0f}ms")

                if self.verbose:
                    print(f"   Response: {result.response_preview}")

                print()

            except Exception as e:
                print(f"   ❌ Error: {e}")
                logger.error(f"Test failed: {test.query}", exc_info=True)
                print()

    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive evaluation report"""

        if not self.results:
            return {"error": "No results to report"}

        # Calculate metrics
        agent_accuracy = sum(r.agent_correct for r in self.results) / len(self.results)
        avg_entity_recall = mean(r.entity_recall for r in self.results)
        avg_latency = mean(r.latency_ms for r in self.results)
        median_latency = median(r.latency_ms for r in self.results)
        total_tokens = sum(r.estimated_tokens for r in self.results)
        estimated_cost = (total_tokens / 1000) * self.cost_per_1k_tokens

        # Category breakdown
        category_stats = {}
        for result in self.results:
            # Find original test case to get category
            test = next((t for t in TEST_CASES if t.query == result.query), None)
            if test:
                if test.category not in category_stats:
                    category_stats[test.category] = {
                        "count": 0,
                        "correct": 0,
                        "avg_recall": []
                    }
                category_stats[test.category]["count"] += 1
                if result.agent_correct:
                    category_stats[test.category]["correct"] += 1
                category_stats[test.category]["avg_recall"].append(result.entity_recall)

        # Calculate category averages
        for cat in category_stats:
            recall_list = category_stats[cat]["avg_recall"]
            category_stats[cat]["avg_recall"] = mean(recall_list) if recall_list else 0
            category_stats[cat]["accuracy"] = category_stats[cat]["correct"] / category_stats[cat]["count"]

        # Find failures
        failures = [r for r in self.results if not r.agent_correct or r.entity_recall < 0.5]

        return {
            "summary": {
                "total_tests": len(self.results),
                "agent_routing_accuracy": agent_accuracy,
                "average_entity_recall": avg_entity_recall,
                "average_latency_ms": avg_latency,
                "median_latency_ms": median_latency,
                "total_estimated_tokens": total_tokens,
                "estimated_cost_usd": estimated_cost
            },
            "category_breakdown": category_stats,
            "failures": [
                {
                    "query": f.query,
                    "expected_agent": f.expected_agent,
                    "detected_agent": f.detected_agent,
                    "entity_recall": f.entity_recall,
                    "missing_entities": f.entities_missing
                }
                for f in failures
            ],
            "timestamp": datetime.now().isoformat()
        }

    def print_report(self, report: Dict[str, Any]):
        """Print formatted evaluation report"""
        print("\n" + "="*60)
        print("📊 NORTH AI EVALUATION REPORT")
        print("="*60)

        summary = report["summary"]
        print(f"\n✨ Overall Metrics:")
        print(f"   Total Tests: {summary['total_tests']}")
        print(f"   Agent Routing Accuracy: {summary['agent_routing_accuracy']:.1%}")
        print(f"   Average Entity Recall: {summary['average_entity_recall']:.1%}")
        print(f"   Average Latency: {summary['average_latency_ms']:.0f}ms")
        print(f"   Median Latency: {summary['median_latency_ms']:.0f}ms")
        print(f"   Total Tokens (estimated): {summary['total_estimated_tokens']:,}")
        print(f"   Estimated Cost: ${summary['estimated_cost_usd']:.4f}")

        print(f"\n📂 Category Breakdown:")
        for category, stats in report["category_breakdown"].items():
            print(f"   {category}:")
            print(f"      Tests: {stats['count']}")
            print(f"      Accuracy: {stats['accuracy']:.1%}")
            print(f"      Avg Recall: {stats['avg_recall']:.1%}")

        if report["failures"]:
            print(f"\n⚠️  Failed Tests ({len(report['failures'])}):")
            for failure in report["failures"]:
                print(f"   • \"{failure['query']}\"")
                print(f"     Expected: {failure['expected_agent']} | Got: {failure['detected_agent']}")
                print(f"     Entity Recall: {failure['entity_recall']:.1%}")
                if failure['missing_entities']:
                    print(f"     Missing: {', '.join(failure['missing_entities'])}")
        else:
            print(f"\n🎉 All tests passed!")

        print("\n" + "="*60)

    def save_report(self, report: Dict[str, Any], filename: str = "evaluation_report.json"):
        """Save detailed report to JSON file"""
        output_path = Path(__file__).parent.parent / "reports" / filename
        output_path.parent.mkdir(exist_ok=True)

        # Add detailed results to report
        full_report = {
            **report,
            "detailed_results": [asdict(r) for r in self.results]
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(full_report, f, indent=2, ensure_ascii=False)

        print(f"\n💾 Detailed report saved to: {output_path}")

    def cleanup(self):
        """Clean up NORTH instance"""
        if self.north:
            try:
                self.north.cleanup()
            except Exception as e:
                print(f"Cleanup error: {e}")


# ==================== MAIN ====================

def main():
    """Main evaluation entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate NORTH AI retrieval quality")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show full responses")
    parser.add_argument("--save", "-s", action="store_true", help="Save detailed report to JSON")
    args = parser.parse_args()

    evaluator = NORTHEvaluator(verbose=args.verbose)

    try:
        # Initialize NORTH
        evaluator.initialize()

        # Run all tests
        evaluator.run_all_tests()

        # Generate and print report
        report = evaluator.generate_report()
        evaluator.print_report(report)

        # Save if requested
        if args.save:
            evaluator.save_report(report)

        # Return exit code based on success
        summary = report["summary"]
        if summary["agent_routing_accuracy"] >= 0.8 and summary["average_entity_recall"] >= 0.7:
            print("\n✅ Evaluation passed quality thresholds")
            return 0
        else:
            print("\n⚠️  Evaluation below quality thresholds (80% routing, 70% recall)")
            return 1

    except KeyboardInterrupt:
        print("\n\nEvaluation interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Evaluation failed: {e}")
        logger.error("Evaluation failed", exc_info=True)
        return 1
    finally:
        evaluator.cleanup()


if __name__ == "__main__":
    sys.exit(main())
