/*
* This script is executed when a new tag is pushed to remote
* The script requires two arguments:
* 1. Full repository name (e.g. internetarchive/openlibrary)
* 2. Latest tag (e.g. deploy-2025-03-20)
* To simulate the script locally, you can use the following command:
* npm install @octokit/rest
* node scripts/gh_scripts/automate_deploy_notes.mjs internetarchive/openlibrary deploy-2025-03-20
* Note: there's a lot of logging in this file and the automate_deploy_notes.yml
* that will be removed when the script is mature
*/

// import { Octokit } from "@octokit/rest"; // for locally testing only
import { Octokit } from "@octokit/action"; // for running in GitHub Actions
import { writeFile } from "fs/promises"

console.log("Script starting to update new tag body....")
// const octokit = new Octokit({ auth: process.env.GITHUB_TOKEN }) // for locally testing only
const octokit = new Octokit() // for running in GitHub Actions
await main()
console.log("Script terminated....")


/*
* This function...
* 1. Compares the second latest tag with the current master branch
* 2. Creates a markdown string with the data returned from 1.
* 3. Updates the body of the latest tag with the markdown string (untested as of now)
*/
async function main() {
  const {fullRepoName, latest_tag} = parseArgs()
  const [repoOwner, repoName] = fullRepoName.split("/")
  console.log(`Repo Owner: ${repoOwner}, Repo Name: ${repoName}, Latest Tag: ${latest_tag}`)

  const compare = await octokit.request("GET /repos/{owner}/{repo}/compare/{base}...{head}", {
    owner: repoOwner,
    repo: repoName,
    base: latest_tag,
    head: "master",
    headers: {
      "X-GitHub-Api-Version": "2022-11-28"
    }
  })
  console.log("Compare Raw data: ", compare.data.commits)

  const notes = await createDeployNotes({
    commits: compare.data.commits,
    repoOwner: repoOwner,
    repoName: repoName
  })
  // const notes = dummyDeployNotes() // local testing only
  console.log("Markdown string:` ", notes)

  const tag = await octokit.request("GET /repos/{owner}/{repo}/releases/tags/{tag}", {
    owner: repoOwner,
    repo: repoName,
    tag: latest_tag,
    headers: {
      "X-GitHub-Api-Version": "2022-11-28"
    }
  })
  const releaseId = tag.data.id
  console.log("Release ID: ", releaseId)
  console.log("Tag Raw data: ", tag.data)

  const release = await octokit.request("PATCH /repos/{owner}/{repo}/releases/{releaseId}", {
    owner: repoOwner,
    repo: repoName,
    releaseId: releaseId,
    body: notes,
    headers: {
      "X-GitHub-Api-Version": "2022-11-28"
    }
  })

  await writeFile('./deploy_notes.md', notes, 'utf-8') // local testing only
  console.log("Deploy notes created successfully")
}

function parseArgs() {
  // Dummy implementation for local testing
  // return {
  //   fullRepoName: "internetarchive/openlibrary",
  //   latest_tag: "deploy-2025-03-20"
  // }
  return {
    fullRepoName: process.argv[2],
    latest_tag: process.argv[3]
  }
}

async function createDeployNotes(parameters) {
  const deployNotes = [{
    heading: {
      text: "What's Changed",
      level: 2
    }
  }]
  for (const commit of parameters.commits) {
    if (commit.author.type === "Bot") {
      continue
    }
    deployNotes.push({commit: {
      message: commit.commit.message,
      author: commit.author.login,
      hash: commit.sha,
      pr: await getPrData({
        repoOwner: parameters.repoOwner,
        repoName: parameters.repoName,
        sha: commit.sha
      })
    }})
  }
  return convertToMarkdown(deployNotes)
}

async function getPrData(parameters) {
  try {
    const commit = await octokit.request("GET /repos/{owner}/{repo}/commits/{commit_sha}/pulls", {
      owner: parameters.repoOwner,
      repo: parameters.repoName,
      commit_sha: parameters.sha
    })
    return {
      number: commit.data[0].number,
      url: commit.data[0].html_url
    }
  }
  catch (error) {
    return 'Unknown: PR likely closed'
  }
}

function convertToMarkdown(deployNotes) {
  let individualCommits = ""
  let merged = "## Merged Pull Requests \r\n"
  deployNotes.forEach((element) => {
    if (element.heading) {
      individualCommits += `${"#".repeat(element.heading.level)} ${element.heading.text}\r\n`
    }
    else if (element.commit.message.startsWith("Merge pull request")) {
      const newLinesRemoved = element.commit.message.replace(/\n/g, " ")
      merged += `* ${newLinesRemoved} by [@${element.commit.author}](https://github.com/${element.commit.author}) in [#${element.commit.pr.number}](${element.commit.pr.url})\r\n`
      return;
    }
    else if (element.commit) {
      const newLinesRemoved = element.commit.message.replace(/\n/g, " ")
      individualCommits += `* ${newLinesRemoved} by [@${element.commit.author}](https://github.com/${element.commit.author}) in [#${element.commit.pr.number}](${element.commit.pr.url})\r\n`
    }
  })
  return individualCommits + "\r\n" + merged
}

/*
I have encountered rate liiting issues with the GitHub API while testing this script
To avoid this, I have created a dummy function that returns a list of commits
This function will be removed once the script is mature
Using authentication will also help avoid rate limiting issues
TODO: Remove this function once the script is mature
*/
function dummyDeployNotes() {
  return [
    {
      heading: {
        text: "What's Changed",
        level: 2,
      },
    },
    {
      commit: {
        message: "nonworking prototype of trusted book provider interstitial",
        author: "mekarpeles",
        hash: "967c5e7fa53676d2d52cf26ac2bc58326e8de2cf",
        pr: {
          number: 10605,
          url: "https://github.com/internetarchive/openlibrary/pull/10605",
        },
      },
    },
    {
      commit: {
        message: "Extract carousel card into dedicated template",
        author: "jimchamp",
        hash: "5ce1fdab425dfe203c6225c5125b49150fb7f359",
        pr: {
          number: 10580,
          url: "https://github.com/internetarchive/openlibrary/pull/10580",
        },
      },
    },
    {
      commit: {
        message: "Move main pertials code into a new file",
        author: "jimchamp",
        hash: "6f5056369b9036eb2e305abae5b0ae57c5201153",
        pr: {
          number: 10580,
          url: "https://github.com/internetarchive/openlibrary/pull/10580",
        },
      },
    },
    {
      commit: {
        message: "move check-in form inside default hidden div\nto prevent it from displaying on mobile safari browser",
        author: "hornc",
        hash: "f4ff8157de6e6a653eafbdba995ef54801505e56",
        pr: {
          number: 10581,
          url: "https://github.com/internetarchive/openlibrary/pull/10581",
        },
      },
    },
    {
      commit: {
        message: "remove duplicate method attribute\nrelates to #10582",
        author: "hornc",
        hash: "9fef0640d208faf5a231a239c8f852a18157335f",
        pr: {
          number: 10581,
          url: "https://github.com/internetarchive/openlibrary/pull/10581",
        },
      },
    },
    {
      commit: {
        message: "Render all carousel cards server-side",
        author: "jimchamp",
        hash: "23bc25f12c0eec802ecf55434c1e98294d5228de",
        pr: {
          number: 10580,
          url: "https://github.com/internetarchive/openlibrary/pull/10580",
        },
      },
    },
    {
      commit: {
        message: "fix i18n",
        author: "mekarpeles",
        hash: "9063d0a10f7824efd575bdb86fb84ca3db2ebd90",
        pr: {
          number: 10605,
          url: "https://github.com/internetarchive/openlibrary/pull/10605",
        },
      },
    },
    {
      commit: {
        message: "Clean up interstitial template and add borrow API behavior for redirection, update read button templates",
        author: "SivanC",
        hash: "970874fb53dc7cb7c2933d9a2552393faafcf20e",
        pr: {
          number: 10586,
          url: "https://github.com/internetarchive/openlibrary/pull/10586",
        },
      },
    },
    {
      commit: {
        message: "Remove toasts from most non-IA book provider templates",
        author: "SivanC",
        hash: "bb82593d7f2ff07c853d7e4ee2783788895debbf",
        pr: {
          number: 10586,
          url: "https://github.com/internetarchive/openlibrary/pull/10586",
        },
      },
    },
    {
      commit: {
        message: "Add interstitial for librivox and direct read previews",
        author: "SivanC",
        hash: "afa211b1eb19f9e77a358cc09a0ae1e392e9c321",
        pr: {
          number: 10586,
          url: "https://github.com/internetarchive/openlibrary/pull/10586",
        },
      },
    },
    {
      commit: {
        message: "remove domain from url",
        author: "mekarpeles",
        hash: "0a138811a39557ec9c04d8c5c66f8c1b8d46da2f",
        pr: {
          number: 10586,
          url: "https://github.com/internetarchive/openlibrary/pull/10586",
        },
      },
    },
    {
      commit: {
        message: "Improve appearance and text of interstitial",
        author: "SivanC",
        hash: "5dda402267633d145587ec62d79a5383d39ba379",
        pr: {
          number: 10586,
          url: "https://github.com/internetarchive/openlibrary/pull/10586",
        },
      },
    },
    {
      commit: {
        message: "Remove domains from remaining templates",
        author: "SivanC",
        hash: "ac553669721eba4943e9720cdd8336de78dfe651",
        pr: {
          number: 10586,
          url: "https://github.com/internetarchive/openlibrary/pull/10586",
        },
      },
    },
    {
      commit: {
        message: "Use BookshelvesEvents for year dropper",
        author: "cdrini",
        hash: "0152ad19f0ce4b41ba28834c7ea462341e091257",
        pr: {
          number: 10599,
          url: "https://github.com/internetarchive/openlibrary/pull/10599",
        },
      },
    },
    {
      commit: {
        message: "Fix yearly dropper never rendering",
        author: "cdrini",
        hash: "cedd7f50b8291bf0c8aad3d27fdbd684bf568f15",
        pr: {
          number: 10599,
          url: "https://github.com/internetarchive/openlibrary/pull/10599",
        },
      },
    },
    {
      commit: {
        message: "Demystify magic number",
        author: "jimchamp",
        hash: "4762d74f96239323a592460a98864dbfdedbe891",
        pr: {
          number: 10580,
          url: "https://github.com/internetarchive/openlibrary/pull/10580",
        },
      },
    },
    {
      commit: {
        message: "Add `production` tag on deployment",
        author: "jimchamp",
        hash: "481102b1639b77e93bd041f8b8fade6e9c32d71f",
        pr: {
          number: 10602,
          url: "https://github.com/internetarchive/openlibrary/pull/10602",
        },
      },
    },
    {
      commit: {
        message: "Update deploy script automate announcement",
        author: "mekarpeles",
        hash: "1849c55db081e8d8dca1dbac9044933f7e8c0352",
        pr: "Unknown: PR likely closed",
      },
    },
    {
      commit: {
        message: "Remove toast related tags, move countdown to JS file",
        author: "SivanC",
        hash: "141bc2478eff01aa12060be89037d82262793e13",
        pr: {
          number: 10586,
          url: "https://github.com/internetarchive/openlibrary/pull/10586",
        },
      },
    },
    {
      commit: {
        message: "Remove comments",
        author: "jimchamp",
        hash: "45ee2979d8fd99752cca475c82fa37d9b4d3553d",
        pr: {
          number: 10586,
          url: "https://github.com/internetarchive/openlibrary/pull/10586",
        },
      },
    },
    {
      commit: {
        message: "Merge pull request #10586 from SivanC/trustedbookprovider-interstitial\n\nMigrate to Interstitial for Trusted Book Provider read actions",
        author: "jimchamp",
        hash: "697896150ae10e7aa4404dd700d7bd5c45498fdb",
        pr: {
          number: 10586,
          url: "https://github.com/internetarchive/openlibrary/pull/10586",
        },
      },
    },
    {
      commit: {
        message: "Merge pull request #10581 from hornc/fix-mobilecheckin\n\nmove check-in form inside conditionally hidden div",
        author: "jimchamp",
        hash: "7ede124a1580f630fc35a2b090129d5a7f446054",
        pr: {
          number: 10581,
          url: "https://github.com/internetarchive/openlibrary/pull/10581",
        },
      },
    },
    {
      commit: {
        message: "Merge pull request #10602 from internetarchive/production-tag\n\nAdd `production` git tag when code is deployed",
        author: "cdrini",
        hash: "2b8086dc55215f2963f92474d52dc437da85613c",
        pr: {
          number: 10602,
          url: "https://github.com/internetarchive/openlibrary/pull/10602",
        },
      },
    },
    {
      commit: {
        message: "Merge pull request #10599 from cdrini/feature/use-bookshelf-events-for-year-selector\n\nEnable Already Read year read drop-down",
        author: "mekarpeles",
        hash: "3602ceaf0257a149279969cd9fc198a4a4dc10a7",
        pr: {
          number: 10599,
          url: "https://github.com/internetarchive/openlibrary/pull/10599",
        },
      },
    },
    {
      commit: {
        message: "Merge pull request #10604 from SivanC/10600/fix/read-panel-read-button-spacing\n\n10600/fix/read panel read button spacing",
        author: "SivanC",
        hash: "298fe55977f0478ae23f5b8808b76e7603f86ed0",
        pr: {
          number: 10604,
          url: "https://github.com/internetarchive/openlibrary/pull/10604",
        },
      },
    },
    {
      commit: {
        message: "Merge branch 'master' into trustedbookprovider-interstitial",
        author: "jimchamp",
        hash: "124e9f2003ff0cabd060d725850d2723194d6226",
        pr: {
          number: 10605,
          url: "https://github.com/internetarchive/openlibrary/pull/10605",
        },
      },
    },
    {
      commit: {
        message: "Remove comment",
        author: "jimchamp",
        hash: "9731176a1716bfdd12b279245537500f5495fa68",
        pr: {
          number: 10605,
          url: "https://github.com/internetarchive/openlibrary/pull/10605",
        },
      },
    },
    {
      commit: {
        message: "Merge pull request #10605 from internetarchive/trustedbookprovider-interstitial\n\nMerge interstitial branch into main branch",
        author: "jimchamp",
        hash: "7696f8c98d1304113cc9ccdc55d40a640259a561",
        pr: {
          number: 10605,
          url: "https://github.com/internetarchive/openlibrary/pull/10605",
        },
      },
    },
    {
      commit: {
        message: "Pass URL as `q` for `BROWSE` queries",
        author: "jimchamp",
        hash: "474f305893af54e917ff470c9c25a258364e05e1",
        pr: {
          number: 10580,
          url: "https://github.com/internetarchive/openlibrary/pull/10580",
        },
      },
    },
    {
      commit: {
        message: "Fix global lists not rendering",
        author: "cdrini",
        hash: "9894f81f9a92de70e261d2f27fb4379f56fb93c4",
        pr: {
          number: 10607,
          url: "https://github.com/internetarchive/openlibrary/pull/10607",
        },
      },
    },
    {
      commit: {
        message: "Edit button not appearing on global lists",
        author: "cdrini",
        hash: "f9f4061d9c000c435057755c2db29abcaa760c36",
        pr: {
          number: 10607,
          url: "https://github.com/internetarchive/openlibrary/pull/10607",
        },
      },
    },
    {
      commit: {
        message: "Use correct URL for `BROWSE` queries",
        author: "jimchamp",
        hash: "09b810a5e1dad8130dea59bf722864e404a3cd27",
        pr: {
          number: 10580,
          url: "https://github.com/internetarchive/openlibrary/pull/10580",
        },
      },
    },
    {
      commit: {
        message: "Fix bulk search failing if missing leading article",
        author: "cdrini",
        hash: "82534ee844795586dffa0f0f105d1443c5523cc4",
        pr: {
          number: 10608,
          url: "https://github.com/internetarchive/openlibrary/pull/10608",
        },
      },
    },
    {
      commit: {
        message: "Fix bug with openai api key field being unclickable",
        author: "cdrini",
        hash: "11212aa859fb3c7652a2fa06f99e701638dc17d3",
        pr: {
          number: 10608,
          url: "https://github.com/internetarchive/openlibrary/pull/10608",
        },
      },
    },
    {
      commit: {
        message: "Merge pull request #10610 from internetarchive/renovate/pypi-gunicorn-vulnerability\n\nUpdate dependency gunicorn to v23 [SECURITY]",
        author: "cdrini",
        hash: "d0ed87123c4ba26823e81097a3bba164db24d20c",
        pr: {
          number: 10610,
          url: "https://github.com/internetarchive/openlibrary/pull/10610",
        },
      },
    },
    {
      commit: {
        message: "add a Vietnamese readme",
        author: "BearSunny",
        hash: "888fff58ba6a953a1c78bbebbdea436769e67430",
        pr: {
          number: 10613,
          url: "https://github.com/internetarchive/openlibrary/pull/10613",
        },
      },
    },
    {
      commit: {
        message: "Fix book byline including spaces around commas",
        author: "cdrini",
        hash: "a4260397e0def870d273f052a39538e05ba71cb4",
        pr: {
          number: 10614,
          url: "https://github.com/internetarchive/openlibrary/pull/10614",
        },
      },
    },
    {
      commit: {
        message: "Merge pull request #10607 from cdrini/fix/global-list-rendering\n\nFix global lists erroring when rendering",
        author: "mekarpeles",
        hash: "96e619527d6b334ec9ca8182c22b8d408f467e4a",
        pr: {
          number: 10607,
          url: "https://github.com/internetarchive/openlibrary/pull/10607",
        },
      },
    },
    {
      commit: {
        message: "Merge pull request #10608 from cdrini/fix/bulk-search-bug\n\nFix some small Bulk Search bugs",
        author: "mekarpeles",
        hash: "97c6f0144553f87f277d6f66bb5b7abee005d217",
        pr: {
          number: 10608,
          url: "https://github.com/internetarchive/openlibrary/pull/10608",
        },
      },
    },
    {
      commit: {
        message: "Merge pull request #10613 from BearSunny/reindex\n\nAdd a Vietnamese readme",
        author: "mekarpeles",
        hash: "1e26b1a786c0ba293edbd02b4ea123fc015340f8",
        pr: {
          number: 10613,
          url: "https://github.com/internetarchive/openlibrary/pull/10613",
        },
      },
    },
    {
      commit: {
        message: "Speed up `npm ci` ~55% by creating separate package.json for storybook stories (#10612)\n\n* Create separate package.json for storybook stories\n\nI found storybook was taking a decent junk of time when npm installing,\nso split it out into a separate package.json . I set the npm commands to\nauto-install the new package.json though, so there should be no breaking\nchanges in anyone's flow. The `npm run storybook` will work as before.\n\nOnly potentialy breaking change is that when storybook is built, it'll\nbuild in stories/storybook-static instead of the root-level\nstorybook-static/.\n\n* Fix stories/ subdir not finding .babelrc\n\n* Disable package-lock.json for stories/ subdir\n\nSince these dependencies are only ever used for local development, they\nare incredibly unlikely to need the rigor associated with\npackage-lock.json, which is usually more important for production-facing\ncode.",
        author: "cdrini",
        hash: "c8a681afdcb60fd539cfff4377037c53925176aa",
        pr: {
          number: 10612,
          url: "https://github.com/internetarchive/openlibrary/pull/10612",
        },
      },
    },
    {
      commit: {
        message: "Merge pull request #10614 from cdrini/fix/author-names-odd-spacing\n\nFix book byline including spaces around commas",
        author: "mekarpeles",
        hash: "4113ee6c5442ec0c6aa263071a0f946f295daa55",
        pr: {
          number: 10614,
          url: "https://github.com/internetarchive/openlibrary/pull/10614",
        },
      },
    },
    {
      commit: {
        message: "Merge pull request #10618 from internetarchive/pre-commit-ci-update-config\n\n[pre-commit.ci] pre-commit autoupdate",
        author: "mekarpeles",
        hash: "d95cd283ae21349364c7bfcd89cd9dcf0d51675d",
        pr: {
          number: 10618,
          url: "https://github.com/internetarchive/openlibrary/pull/10618",
        },
      },
    },
    {
      commit: {
        message: "Merge pull request #10580 from jimchamp/5407/update-carousel-with-partials\n\nUpdate carousels using server-side rendered HTML",
        author: "mekarpeles",
        hash: "86e3d2182035c4527a3abeee60e47873a545fe94",
        pr: {
          number: 10580,
          url: "https://github.com/internetarchive/openlibrary/pull/10580",
        },
      },
    },
  ]
}