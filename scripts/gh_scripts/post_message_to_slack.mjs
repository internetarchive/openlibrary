async function publishToSlack(message, slackChannel) {
  const bearerToken = process.env.SLACK_TOKEN
  return fetch('https://slack.com/api/chat.postMessage', {
      method: 'POST',
      headers: {
          'Content-Type': 'application/json;  charset=utf-8',
          Authorization: `Bearer ${bearerToken}`
      },
      body: JSON.stringify({
          channel: slackChannel,
          text: message
      })
  })
}