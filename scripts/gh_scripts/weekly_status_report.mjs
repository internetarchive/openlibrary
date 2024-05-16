import fs from 'node:fs'
import { Octokit } from "@octokit/action";

const octokit = new Octokit()

main()

function main() {
    const config = getConfig()
    console.log(config)
}

function getConfig() {
    if (process.argv.length < 3) {
      throw new Error("Unexpected amount of arguments")
    }
    const configPath = process.argv[2]
    try {
        return JSON.parse(fs.readFileSync(configPath, 'utf8'))
    } catch (err) {
        throw err
    }
}