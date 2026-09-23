import unittest

from knowledge_base import ProductionKnowledgeBase


class PolicyGroundingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = ProductionKnowledgeBase()

    def test_source_and_conflicting_minimum(self):
        answer = self.kb.query("What is the minimum business loan amount?")
        self.assertTrue(answer["found"])
        self.assertEqual(answer["page"], 1)
        self.assertIn("Minimum Loan Amount", answer["content"])
        self.assertIn("data_quality_warning", answer)
        self.assertNotIn("@securebank.in", answer["content"])

    def test_unavailable_facts_do_not_cross_markets(self):
        self.assertFalse(self.kb.query("What is the weather tomorrow?")["found"])
        self.assertFalse(self.kb.query("What is the insurance premium?", market="philippines")["found"])


if __name__ == "__main__":
    unittest.main()
