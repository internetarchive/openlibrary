import { themes as prismThemes } from "prism-react-renderer";
import type { Config } from "@docusaurus/types";
import type * as Preset from "@docusaurus/preset-classic";

const config: Config = {
  title: "Open Library API Docs",
  tagline: "Developer documentation for Open Library APIs",
  favicon: "img/favicon.ico",
  future: {
    v4: true,
  },
  url: "https://openlibrary.org",
  baseUrl: "/dev/docs/",
  organizationName: "internetarchive",
  projectName: "openlibrary",
  onBrokenLinks: "throw",
  i18n: {
    defaultLocale: "en",
    locales: ["en"],
  },
  presets: [
    [
      "classic",
      {
        docs: {
          sidebarPath: "./sidebars.ts",
          routeBasePath: "/",
          editUrl:
            "https://github.com/internetarchive/openlibrary/tree/master/docs/",
        },
        blog: false,
        theme: {
          customCss: "./src/css/custom.css",
        },
      } satisfies Preset.Options,
    ],
  ],
  themeConfig: {
    image: "img/docusaurus-social-card.jpg",
    colorMode: {
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: "Open Library API",
      logo: {
        alt: "Open Library Logo",
        src: "img/logo.svg",
      },
      items: [
        {
          type: "docSidebar",
          sidebarId: "tutorialSidebar",
          position: "left",
          label: "Documentation",
        },
        {
          href: "https://github.com/internetarchive/openlibrary",
          label: "GitHub",
          position: "right",
        },
      ],
    },
    footer: {
      style: "dark",
      links: [
        {
          title: "Docs",
          items: [
            {
              label: "Getting Started",
              to: "/api/getting-started",
            },
            {
              label: "Search API",
              to: "/api/search",
            },
          ],
        },
        {
          title: "Community",
          items: [
            {
              label: "Slack",
              href: "https://openlibrary.org/slack",
            },
            {
              label: "Developer Portal",
              href: "https://openlibrary.org/dev",
            },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} Internet Archive. Built with Docusaurus.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ["python", "bash", "json", "ruby", "go", "php"],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
