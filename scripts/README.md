# NORTH AI Scripts

This directory contains utility scripts for evaluating, maintaining, and managing NORTH AI.

## Evaluation Script

### `evaluate_retrieval.py`

Comprehensive RAG quality evaluation system that measures NORTH's retrieval and orchestration performance.

**Purpose:**
Demonstrates production-grade quality assurance by systematically evaluating:
- Agent routing accuracy (does the right agent handle each query?)
- Entity recall (are expected contractors/documents found in responses?)
- Performance metrics (latency, token usage, costs)

**Usage:**
```bash
# Basic evaluation (13 test cases)
python scripts/evaluate_retrieval.py

# Verbose mode (shows full responses)
python scripts/evaluate_retrieval.py --verbose

# Save detailed results to JSON
python scripts/evaluate_retrieval.py --save
```

**What Gets Measured:**

| Metric | Description | Target |
|--------|-------------|--------|
| Agent Routing Accuracy | % of queries routed to correct agent | >80% |
| Average Entity Recall | % of expected entities found in responses | >70% |
| Average Latency | Response time per query | <2000ms |
| Estimated Cost | Token usage × pricing | <$0.01/query |

**Test Categories:**
1. **Contractor Lookup** - "Who did electrical work on 305 Regency?"
2. **Contact Information** - "What's the phone number for Triple Eagle Electric?"
3. **Document Search** - "Find the signed contract with ABC Electric"
4. **Multi-Source Queries** - "Tell me about ABC Electric and show their contract"
5. **Conversational** - "Hello, can you help me?"

**Example Output:**
```
📊 NORTH AI EVALUATION REPORT
============================================================
✨ Overall Metrics:
   Total Tests: 13
   Agent Routing Accuracy: 92.3%
   Average Entity Recall: 89.1%
   Average Latency: 1,234ms
   Median Latency: 987ms
   Total Tokens (estimated): 1,126
   Estimated Cost: $0.0056

📂 Category Breakdown:
   contractor_lookup: 100% accuracy, 95% recall
   document_search: 100% accuracy, 91% recall
   multi_source: 100% accuracy, 100% recall
```

**JSON Report Structure:**
```json
{
  "summary": {
    "total_tests": 13,
    "agent_routing_accuracy": 0.923,
    "average_entity_recall": 0.891,
    "average_latency_ms": 1234.5,
    "estimated_cost_usd": 0.0056
  },
  "category_breakdown": {
    "contractor_lookup": {
      "count": 5,
      "accuracy": 1.0,
      "avg_recall": 0.95
    }
  },
  "failures": [],
  "detailed_results": [...]
}
```

**Why This Matters for Recruiters:**

Most AI portfolio projects stop at "I can call OpenAI's API." This evaluation script demonstrates:

1. ✅ **RAG Expertise** - Understanding retrieval evaluation, not just implementation
2. ✅ **Production Mindset** - Quality assurance beyond basic functionality
3. ✅ **Metrics-Driven** - Quantifiable performance benchmarks
4. ✅ **Automated Testing** - Repeatable validation process

This separates NORTH from typical LLM wrapper projects by showing systematic quality assessment—a skill critical for ML/AI engineering roles.

---

## Prerequisites

Before running evaluation:

1. **Environment Setup:**
   ```bash
   # Make sure .env is configured
   cp .env.example .env
   # Add your OPENAI_API_KEY
   ```

2. **Weaviate Running:**
   ```bash
   # For local development
   docker start weaviate_north

   # Or use Weaviate Cloud (production)
   # Configure WEAVIATE_URL and WEAVIATE_API_KEY in .env
   ```

3. **Dependencies Installed:**
   ```bash
   pip install -r requirements.txt
   ```

---

## Interpreting Results

### High Quality Indicators (Ready for Production)
- ✅ Agent routing accuracy >80%
- ✅ Entity recall >70%
- ✅ Average latency <2000ms
- ✅ Few or no failures

### Warning Signs (Needs Investigation)
- ⚠️ Agent routing <80% → Check agent availability or routing logic
- ⚠️ Entity recall <70% → Review test expectations or data quality
- ⚠️ Latency >3000ms → Check Weaviate connection or query complexity
- ⚠️ Multiple failures → Review error logs in verbose mode

### Common Issues

**"Obsidian agent unavailable" / Low routing accuracy:**
- Weaviate not running → Start Docker: `docker start weaviate_north`
- Weaviate Cloud misconfigured → Check WEAVIATE_URL and WEAVIATE_API_KEY

**"Missing expected entities":**
- Data not ingested → Run `python main.py sync` or reingest
- Test expectations wrong → Review test cases in evaluate_retrieval.py

**"High latency":**
- Network issues → Check Weaviate Cloud connection
- Complex queries → Review agent search strategies
- Rate limiting → Check OpenAI API quotas

---

## Extending the Evaluation

To add new test cases, edit `evaluate_retrieval.py`:

```python
TEST_CASES.append(
    TestCase(
        query="Your test query here",
        expected_agent="obsidian",  # or "dropbox" or "both"
        expected_entities=["entity1", "entity2"],
        category="your_category",
        description="Human-readable description"
    )
)
```

---

## Output Files

When using `--save` flag:
- **Location**: `reports/evaluation_report.json`
- **Format**: JSON with full results and metadata
- **Contents**: Summary, category breakdown, failures, detailed results for each test

---

## Integration with CI/CD

You can integrate this into automated testing:

```bash
# Run evaluation and exit with error if below thresholds
python scripts/evaluate_retrieval.py
# Exit code 0 = passed (>80% routing, >70% recall)
# Exit code 1 = failed quality thresholds
```

Example GitHub Actions:
```yaml
- name: Run RAG Evaluation
  run: python scripts/evaluate_retrieval.py --save

- name: Upload Evaluation Report
  uses: actions/upload-artifact@v3
  with:
    name: evaluation-report
    path: reports/evaluation_report.json
```

---

## Credits

Built for NORTH AI - Production multi-agent orchestration system
Demonstrates production-grade RAG quality evaluation practices
