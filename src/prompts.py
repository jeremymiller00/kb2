SUMMARY_SYSTEM = "You are a helpful assistant that creates concise, informative summaries."

SUMMARY_TEMPLATES = {
    "general": (
        "Summarize the following article in about 100 words. "
        "Focus on: the main topic, key arguments or findings, "
        "comparisons made, and implications or conclusions.\n\n{content}"
    ),
    "arxiv": (
        "Summarize the following research paper in about 100 words. "
        "Focus on: the main problem being solved, methodology used, "
        "key results, comparison to prior work, potential applications, "
        "and limitations.\n\n{content}"
    ),
    "github": (
        "Summarize the following GitHub repository in about 100 words. "
        "Focus on: the purpose of the project, key features, "
        "technology stack, and notable aspects.\n\n{content}"
    ),
    "youtube": (
        "Summarize the following video transcript in about 150 words. "
        "Focus on: the main topic, key concepts discussed, "
        "arguments or findings presented, methodologies mentioned, "
        "and key takeaways.\n\n{content}"
    ),
    "huggingface": (
        "Summarize the following model page in about 100 words. "
        "Focus on: the model architecture, training data, "
        "performance metrics, intended use cases, and limitations.\n\n{content}"
    ),
}

KEYWORD_PROMPT = (
    "Extract 5-10 keywords from the following summary. "
    "Return them as a comma-separated list. Use lowercase. "
    "Keywords should be suitable as Obsidian tags (no spaces — use hyphens for multi-word tags).\n\n{summary}"
)

