// @ts-check
/**
 * Util script to restart solr. This file should probably be using something built
 * into docker compose, but that looks like it's not quite available
 * for docker compose? It might be docker swarm only? It's unclear.
 *
 * This script is necessary to prevent solr from going occasionally going down
 * in-explicably. Well, it doesn't prevent it, but it force it to restart after ~3min
 * of "unhealthy".
 */
const { execSync } = require('child_process');
const fetch = require('node-fetch');


/**
 * @param {number} ms
 */
async function sleep(ms) {
    return new Promise(res => setTimeout(() => res(), ms));
}

class SolrRestarter {
    /** Don't restart twice in 10 minutes */
    MAX_RESTART_WIN = 10*60*1000;
    /** Must be unhealthy for this many minutes to trigger a refresh */
    UNHEALTHY_DURATION = 2*60*1000;
    /** Check every minute */
    CHECK_FREQ = 60*1000;
    /** How many times we're aloud to try restarting without going healthy before giving up */
    MAX_RESTARTS = 3;
    /** Number of restarts we've done without transitioning to healthy */
    restartsRun = 0;
    /** timestamp in ms */
    lastRestart = 0;
    /** @type {'healthy' | 'unhealthy'} */
    state = 'healthy';
    /** timestamp in ms */
    lastStateChange = 0;
    /** Number of consecutive health checks that haven't failed or succeeded, but errored. */
    healthCheckErrorRun = 0;

    /** The URL to fetch in our healthcheck */
    TEST_URL = process.env.TEST_URL ?? 'http://openlibrary.org/search.json?q=hello&mode=everything&limit=0';

    /** Whether we should send slack messages, or just console.log */
    SEND_SLACK_MESSAGE = process.env.SEND_SLACK_MESSAGE == 'true';

    /** The containers to restart */
    CONTAINER_NAMES = process.env.CONTAINER_NAMES;

    async checkHealth() {
        console.log(this.TEST_URL);
        const resp = await Promise.race([fetch(this.TEST_URL), sleep(3000).then(() => 'timeout')]);

        if (resp == 'timeout') return false;

        try {
            const json = await resp.json();
            return !json.error && json.numFound;
        } catch (err) {
            throw `Invalid response: ${await resp.text()}`;
        }
    }

    /**
     * @param {string} text
     */
    async sendSlackMessage(text) {
        if (this.SEND_SLACK_MESSAGE) {
            await fetch('https://slack.com/api/chat.postMessage', {
                method: 'POST',
                headers: {
                    Authorization: `Bearer ${process.env.SLACK_TOKEN}`,
                    "Content-Type": "application/json; charset=utf-8",
                },
                body: JSON.stringify({
                    text,
                    channel: process.env.SLACK_CHANNEL_ID,
                })
            }).then(r => r.text());
        } else {
            console.log(text);
        }
    }

    async loop() {
        while (true) {
            let isHealthy = true;
            try {
                isHealthy = await this.checkHealth();
            } catch (err) {
                this.healthCheckErrorRun++;
                if (this.healthCheckErrorRun > 3) {
                    // This is an unexpected error; likely means OL is down for other reasons.
                    await this.sendSlackMessage(`Health check errored 3+ times with ${err}; skipping?`);
                }
                await sleep(this.CHECK_FREQ);
                continue;
            }
            this.healthCheckErrorRun = 0;
            const newState = isHealthy ? 'healthy' : 'unhealthy';
            if (this.state != newState) {
                this.lastStateChange = Date.now();
            }
            this.state = newState;
            console.log(`State: ${this.state}`);

            if (!isHealthy) {
                if (Date.now() - this.lastStateChange > this.UNHEALTHY_DURATION) {
                    const canRestart = Date.now() - this.lastRestart > this.MAX_RESTART_WIN;
                    if (canRestart) {
                        if (this.restartsRun >= this.MAX_RESTARTS) {
                            await this.sendSlackMessage("Hit max restarts. we're clearly not helping. Exiting.");
                            throw new Error("MAX_RESTARTS exceeded");
                        }
                        await this.sendSlackMessage(`solr-restarter: Unhealthy for a few minutes; Restarting solr`);
                        execSync(`docker restart ${this.CONTAINER_NAMES}`, { stdio: "inherit" });
                        this.restartsRun++;
                        this.lastRestart = Date.now();
                    } else {
                        console.log('Cannot restart; too soon since last restart');
                    }
                }
            } else {
                // Send a message if we recently tried to restart
                if (this.restartsRun) {
                    await this.sendSlackMessage(`solr-restarter: solr state now ${this.state} :success-kid:`);
                }
                this.restartsRun = 0;
            }
            await sleep(this.CHECK_FREQ);
        }
    }
}

process.on('unhandledRejection', err => { throw err });
new SolrRestarter().loop();
