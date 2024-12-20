# TWA

Trusted Web Activity is a new way to open your web-app content such as your Progressive Web App (PWA) from your Android app using a protocol based on Custom Tabs.

## Bubblewrap CLI

Bubblewrap is a Command Line Interface (CLI) that helps developers to create a Project for an Android application that launches an existing Progressive Web App (PWA) using a Trusted Web Activity (TWA).

## Setting up the Environment

When running Bubblewrap for the first time, it will offer to automatically download and install
external dependencies.

## Quickstart Guide

### Installing Bubblewrap

```shell
npm i --no-audit -g @bubblewrap/cli
```

### Initializing an Android Project
Generate an Android project from an existing Web Manifest:

```shell
bubblewrap init --manifest https://openlibrary.org/static/manifest.json
```

It will also ask you for the details needed to generate a signing key, used to sign the
app before uploading to the Play Store.

### Building the Android Project
```shell
bubblewrap build
```
