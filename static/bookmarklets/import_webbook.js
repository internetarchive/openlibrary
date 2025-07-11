javascript:(async()=> {
  const url = prompt("ðŸ“š Enter the book URL you want to import:");
  if (!url) return;
  const promptText = `You are an expert book metadata librarian and research assistant.
Your role is to search the web and collect accurate data to produce the most useful, factual, complete, and patron-oriented book page possible for the URL:

Book URL: ${url}

---

ðŸŽ¯ Overall Behavior Guidelines:

- âœ… Use both your training knowledge AND search the web for this book url.
- âœ… Prefer the web page content over assumptions.
- âœ… Prioritize accuracy, depth, and patron usefulness.
- âœ… Take time and thoroughly analyze the web page, looking for a book cover image, author info, publication details, and file format clues.
- âœ… When uncertain, leave fields empty (or use specified defaults). Do not hallucinate.
- âœ… If something is not explicitly available or verifiable, leave it out or follow the specified missing-value rule.

---

â›“ï¸  Output Constraints (Critical):

âœ… Your final output must be a single, clean, parsable JSONL object in a code block all on a single line in jsonl format (matching the schema and rules below) with no markdown, no commentary, and no prose outside the JSON code block.
âœ… Safety & Quality Check:
If the provided URL appears fundamentally unsound, spammy / phishy, malicious / malicious, deceptive, highly self-promotional, overtly pirated (DMCA-violating), poses an imminent risk of harm, or is extremely low quality, you must abort and respond with a reasonable JSON object like: \`{"error": "suspected spam"}\`
âœ… Required JSON Schema:
\`\`\`
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
  - Follow with additional long-form sections (as applicable and only if they add value) using optional headings like:
    - "Key Topics" and/or "Key Themes"
    - "Key Insights" / "Quotes" / "Notable Exerpts"
    - What makes it great or unique v. similar books? "Reception" or "Accolades"
    - Select Questions and Answers (based on the content)
    - Criticisms about the book content or structure?
    - Content Features (what is notable about the book format, structure)
    - Notable public citations (in books, academic papers or the web)
    - "About the Book", "Audience", "Critical Reception"
    - Cultural or Societal Significance (if relevant)
    - Notes about this specific edition? (anything new, improved, etc)

- "subjects":
  - A flat array of concise tags that help patrons search or filter books.
  - Include subject matter (topics, genres, fields of study).
  - Also include any distinctive book qualities, prefixed as follows (but only if they help a patron search or filter):
    - "is:nonfiction", "is:textbook", "is:compendium", etc. (only when truly appropriate)
    - "has:illustrations", "has:exercises", etc. for content features
  - Overall, only include tags that provide real patron value.

- "cover":
  - If unknown, do NOT make up a cover url; this is anti-helpful
  - Direct URL to the bookâ€™s cover image.
  - Finding a correct cover is a priority, this may require carefully examining the web page, including any images or Open Graph metadata (og:image), to find the best cover.
  - If a cover is clearly present on the page, include it.
  - If no cover is found, leave this field as an empty string ("").

- "source_records": Always include: ["ChatGPT:\${url}"] but without scheme (i.e. no http:// or https://)

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
  - Otherwise, omit the field entirely.

- "providers":
  - Must reflect the actual format of the book as inferred from the web page:
    - "pdf", "epub", "html", "web", etc.
  - Always set "access": "read" and "provider_name": "Open Library Community Librarians".

- "mentions":
  - Only include this field if you have 1 or more reputable external review links (from respected sources like journals, newspapers, blogs).
  - Otherwise, omit the field entirely.
`;

  // Step 1: Open ChatGPT with pre-filled prompt
  const chatUrl = "https://chatgpt.com/?q=" + encodeURIComponent(promptText);
  window.open(chatUrl, "_blank", "width=1000,height=800,menubar=no,toolbar=no,location=no,status=no,scrollbars=yes");

  //window.location.href = "/api/import/batch/new";
    
  // Step 2: Prompt user to paste ChatGPT's JSON response
  const jsonText = prompt("âœ… After running the ChatGPT prompt and getting the JSON, paste the full JSON output here:");

  if (!jsonText) return alert("âŒ No JSON pasted. Import cancelled.");

  let payload;
  try {
    payload = JSON.parse(jsonText);
  } catch (e) {
    console.error("Invalid JSON:", e);
    return alert("âŒ Invalid JSON. Check the console for details.");
  }

  try {
    const resp = await fetch("https://openlibrary.org/api/import", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    const data = await resp.json();
    console.log("âœ… Open Library API Response:", data);

    if (data && data.url) {
      alert(`âœ… Import successful! View your new book at:\n\n${data.url}`);
      window.open(data.url, "_blank");
    } else {
      alert("âœ… Import complete! Check console for details.");
    }

  } catch (e) {
    console.error("âŒ Import failed:", e);
    alert("âŒ Error posting to Open Library. Check console.");
  }
})();
