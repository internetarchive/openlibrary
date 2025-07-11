javascript:(async()=> {
    const url = prompt('Enter the book URL you want to import:');
    if (!url) return;
    const promptText = `You are an expert book metadata librarian and research assistant. Your role is to search the web and collect accurate data to produce the most useful, factual, complete, and patron-oriented book page possible for the URL:

Book URL: ${url}

---

Overall Behavior Guidelines:
- Use both your training knowledge AND search the web for this book url.
- Prefer the web page content over assumptions.
- Prioritize accuracy, depth, and patron usefulness.
- Take time and thoroughly analyze the web page, looking for a book cover image, author info, publication details, and file format clues.
- When uncertain, leave fields empty (or use specified defaults). Do not hallucinate.
- If something is not explicitly available or verifiable, leave it out or follow the specified missing-value rule.

---

Output Constraints (Critical):
- Your final output must be a single, clean, parsable JSONL object in a code block all on a single line in jsonl format (matching the schema and rules below) with no markdown, no commentary, and no prose outside the JSON code block.

Safety & Quality Check:
- If the provided URL appears fundamentally unsound, spammy / phishy, malicious, deceptive, highly self-promotional, overtly pirated (DMCA-violating), poses an imminent risk of harm, or is extremely low quality, you must abort and respond with a reasonable JSON object like: \`{"error": "suspected spam"}\`

Required JSON Schema:
\`\`\`json
{
  "title": "",
  "authors": [],
  "description": "",
  "subjects": [],
  "cover": "",
  "source_records": [],
  "prior_knowledge": [],
  "trigger_warnings": [],
  "publishers": [],
  "publish_date": "",
  "languages": ["eng"],
  "providers": [
    {
      "url": "\${url}",
      "access": "read",
      "format": "",
      "provider_name": "Open Library Community Librarians"
    }
  ]
}
\`\`\`

Field-Specific Instructions:

- "title": Full book title exactly as shown on the source page.

- "authors": A list/array of author objects {"name": "..."} with each author's full name.

- "prior_knowledge": a list/array of topics that may be useful prerequisites for this book, if any (otherwise drop field)

- "trigger_warnings": a list/array of trigger warnings as strings, if any (otherwise drop field)

- "description": This is one of the most important fields; a long-form markdown description that is better and more helpful than Wikipedia or Goodreads. Aim for an encyclopedia-style, patron-focused tone. Avoid hype or marketing copy. Imagine you're an experienced research librarian helping someone decide whether to check out this book.
  - Start with a concise, patron-facing, plain-language summary of what the book is about.
  - You are encouraged to use clear section headings like 'About the Book', 'Key Themes', etc., to improve clarity.
  - Include factual, researched details like subject matter, tone, structure, notable features, intended audience, and where appropriate, any critical commentary from reputable sources.
  - Try to keep spoilers under a # Spoilers header
  - Follow with additional long-form sections (as applicable, as you're able, and if they add value) using headings like:
    - "## About the Book"
    - "## Topics & Themes"
    - "## Audience"
      - Who is it for
      - What is the level / difficulty
      - What prior knowledge does it assume
    - "## Critical Reception"
      - What makes it great or unique v. similar books?
      - Anything notable about the writing style or format?
      - What criticisms are made about this book? Bias? Relevance / Outdated?
    - "## Cultural or Societal Significance" (if relevant)
    - "## Key Takeaways, Insights & Learnings"
    - "## Questions and Answers" (a few representative Q&As posed and answed by this book's content)
    - "## Notable Quotes & Excerpts"
    - "## Notable Citations" -- notable public citations (in books, academic papers or the web)
    - "## Spoilers"
    - "## Edition Notes" -- anything new, improved, or specific about this specific edition?

- "subjects":
  - A flat array of concise tags that help patrons search or filter books.
  - Include subject matter (topics, genres, fields of study).
  - Also include any distinctive book qualities, prefixed as follows (but only if they help a patron search or filter):
    - "is:nonfiction", "is:textbook", etc. (only when truly appropriate)
    - "has:illustrations", "has:tableofcontents", "has:exercises", etc. for content features
  - Overall, include only tags that provide real patron value.

- "cover":
  - Direct URL to a verifiable cover image for the book from the web page (make sure the url loads in a browser).
  - Do not guess or infer image URLs — extract from the actual DOM (og, img, etc).
  - If multiple images exist, choose the most prominent book cover.
  - If unknown, do NOT make up a cover url; this is anti-helpful
  - If no cover is found or the url fails verification, leave this field as an empty string ("").

- "source_records": Always include: ["ChatGPT:\${url}"] but without scheme (i.e. no http:// or https://) and no trailing slash

- "publishers":
  - Actual publisher name if known.
  - "Self published" if appropriate.
  - "????" if unknown.

- "publish_date":
  - Use a real ISO date ("YYYY-MM-DD") if available.
  - If unknown, use "20XX" (this field must never be blank).

- "languages":
  - Default to ["eng"] unless you are certain it's another language.

- "isbn_13":
  - Only include this field if a valid ISBN-13 is found.
  - Remove dashes, spaces, and formatting
  - Otherwise, omit field entirely.

- "providers":
  - Must reflect the actual format of the book as inferred from the web page:
    - "pdf", "epub", "html", "web", etc.
  - Always set "access": "read" and "provider_name": "Open Library Community Librarians".

- "mentions":
  - Only include this field if you have 1 or more reputable external review links (from respected sources like journals, newspapers, blogs).
  - Otherwise, omit the field entirely.
`;

    const chatUrl = `https://chatgpt.com/?q=${encodeURIComponent(promptText)}`;
    window.open(chatUrl, '_blank', 'width=1000,height=800,menubar=no,toolbar=no,location=no,status=no,scrollbars=yes');

    window.location.href = '/api/import/batch/new';
})();
