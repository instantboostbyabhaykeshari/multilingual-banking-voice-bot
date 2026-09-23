"""Run five knowledge-base retrieval checks and print results to the terminal.

This script does not start the microphone, Gemini Live, or nudge classifier.
It only loads the approved policy PDF and tests semantic retrieval.
"""

from knowledge_base import ProductionKnowledgeBase


QUERIES = [
    ("PRODUCT", "What business loan products are available?"),
    ("POLICY", "What documents are required for a business loan?"),
    ("QUALIFICATION", "What are the eligibility requirements for a business loan?"),
    ("FAQ", "How does loan repayment or tenure work?"),
    ("OBJECTION", "The EMI is too high. Are there any payment options?"),
]


def main() -> None:
    print("Building the knowledge base from the policy PDF...\n")
    kb = ProductionKnowledgeBase()

    for number, (category, question) in enumerate(QUERIES, start=1):
        result = kb.query(question, market="india")

        print("=" * 80)
        print(f"Query {number} [{category}]")
        print(f"User question: {question}")
        print(f"Found: {result.get('found')}")

        if result.get("found"):
            print(f"Relevance score: {result.get('score')}")
            print(f"Source: {result.get('source')}")
            print(f"Page: {result.get('page')}")
            print("Retrieved chunk:")
            print(result.get("content", ""))
            if result.get("data_quality_warning"):
                print(f"Data-quality warning: {result['data_quality_warning']}")
        else:
            print(f"Reason: {result.get('reason')}")

    print("=" * 80)
    print("Retrieval check complete. Copy the five outputs into retrieval_evaluation.md.")


if __name__ == "__main__":
    main()
