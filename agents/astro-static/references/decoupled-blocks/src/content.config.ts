import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

// Astro reads the same files Tina writes. No Tina client involved — the page
// is built from plain markdown frontmatter, so the build can never fail on a
// CMS query and the output carries no editing runtime.
const pages = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./content/pages" }),
  schema: z.object({
    title: z.string(),
    blocks: z.array(z.any()).default([]),
  }),
});

export const collections = { pages };
