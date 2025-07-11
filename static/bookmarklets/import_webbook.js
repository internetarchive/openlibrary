javascript:(async()=> {
    const url = prompt('Enter the book URL you want to import:');
    if (!url) return;
    const promptText = `You are an expert book metadata librarian and research assistant. Your role is to search the web and collect accurate data to produce the most useful, factual, complete, and patron-oriented book page possible for the URL:

Book URL: ${url}

---

Overall Behavior Guidelines:
- Use "search the web" for the url and thoroughly analyze the result for book cover image, author info, publication details, and file format clues
- Use your training knowledge if available and reliable.
- Prioritize accuracy, depth, and patron usefulness.
- Do not hallucinate: If something is not uncertain or not explicitly available or verifiable, leave it out or follow the specified missing-value rule.

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

- "subjects": A flat array of concise tags that help patrons search or filter books.
  - Include subject matter (topics, genres, fields of study). e.g. ["mathematics", "linear algebra", "determinants"]
  - Also include any distinctive book qualities, prefixed as follows (but only if they help a patron search or filter):
    - "is:nonfiction", "is:textbook", etc. (only when truly appropriate)
    - "has:illustrations", "has:table-of-contents", "has:exercises", etc. for content features
  - Overall, include only tags that provide real patron value.

- "prior_knowledge": a list/array of topics that may be useful prerequisites for this book, if any (otherwise drop field)

- "trigger_warnings": a list/array of trigger warnings as strings, if any (otherwise drop field)

- "description": This is one of the most important fields; a long-form markdown description that is better and more helpful than Wikipedia or Goodreads. Aim for an encyclopedia-style, patron-focused tone. Avoid hype or marketing copy. Imagine you're an experienced research librarian helping someone decide whether to check out this book.
  - Start with a concise, patron-facing, plain-language summary of what the book is about.
  - Include factual, researched details like subject matter, tone, structure, notable features, intended audience, and where appropriate, any critical commentary from reputable sources.
  - Follow with additional long-form sections (as applicable, as you're able, and if they add value) using headings like:
    - "## About the Book"
    - "## Topics & Themes"
    - "## Audience"
      - Who is it for, what is the level / difficulty, what prior knowledge does is assumed
    - "## Critical Reception"
      - What makes it great or unique, esp v. similar books?
      - What criticisms are made about the book? Bias? Relevance / Outdated?
    - "## Cultural or Societal Significance" (if relevant, like wikipedia)
    - "## Key Takeaways, Learnings & Insights"
    - "## Select Questions and Answers" (a few representative Q&As posed and answed by this book's content)
    - "## Notable Quotes & Excerpts"
    - "## Notable Mentions"
      - verifiable books, academic papers, or live web pages citing this book
    - "## Spoilers"
    - "## Edition Notes" -- anything new, improved, or specific about this specific edition?

- "cover":
  - Verifiable URL to book cover image (make sure the cover url is valid and loads in a browser).
  - Do not guess or infer image URLs — extract from the actual DOM (og, img, etc).
  - If no cover, default to empty string ("").

- "source_records": Always include: ["ChatGPT:\${url}"] but without scheme (i.e. no http:// or https://) and no trailing slash

- "publishers":
  - Actual publisher name if known.
  - "Self published" if appropriate.
  - "????" if unknown.

- "publish_date":
  - Use a real ISO date ("YYYY-MM-DD") if known
  - Else use "20XX" (field must never be blank).

- "languages":
  - ["eng"] unless you are certain it's another language.

- "isbn_13":
  - Only include this field if a valid ISBN-13 is found.
  - Remove dashes, spaces, and formatting
  - Otherwise, omit field entirely.

- "providers":
  - Must reflect the actual format of the book as inferred from the web page:
    - "pdf", "epub", "html", "web", etc.
  - Always set "access": "read" and "provider_name": "Open Library Community Librarians".`;

    const chatUrl = `https://chatgpt.com/?q=${encodeURIComponent(promptText)}`;
    window.open(chatUrl, '_blank', 'width=1000,height=800,menubar=no,toolbar=no,location=no,status=no,scrollbars=yes');
})();
