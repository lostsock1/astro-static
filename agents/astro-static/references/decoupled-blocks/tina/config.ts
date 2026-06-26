import { defineConfig } from "tinacms";

// Local, git-backed mode (no Tina Cloud). The admin is the ONLY Tina runtime;
// the published Astro site never imports Tina — it just reads these markdown
// files. That decoupling is what keeps the output lean + the editing reliable.
export default defineConfig({
  branch: "",
  clientId: "",
  token: "",
  build: { outputFolder: "admin", publicFolder: "public" },
  media: { tina: { mediaRoot: "uploads", publicFolder: "public" } },
  schema: {
    collections: [
      {
        name: "page",
        label: "Pages",
        path: "content/pages",
        format: "md",
        ui: {
          router: ({ document }) =>
            document._sys.filename === "home" ? "/" : `/${document._sys.filename}`,
        },
        fields: [
          { type: "string", name: "title", label: "Title", isTitle: true, required: true },
          {
            // The blocks field: editors add / remove / reorder typed sections.
            // This is the "fully customizable" surface — reliable, git-backed.
            // Each template below MUST mirror an Astro component in
            // src/components/blocks/ and a registry entry in src/pages/index.astro.
            type: "object",
            name: "blocks",
            label: "Sections",
            list: true,
            ui: {
              visualSelector: true,
              itemProps: (item) => ({ label: `▸ ${item?._template ?? "section"}` }),
            },
            templates: [
              {
                name: "hero",
                label: "Hero",
                fields: [
                  { type: "string", name: "eyebrow", label: "Eyebrow" },
                  { type: "string", name: "heading", label: "Heading" },
                  { type: "string", name: "subheading", label: "Subheading", ui: { component: "textarea" } },
                  { type: "string", name: "ctaText", label: "Button Text" },
                ],
              },
              {
                name: "features",
                label: "Features",
                fields: [
                  { type: "string", name: "heading", label: "Heading" },
                  {
                    type: "object",
                    name: "items",
                    label: "Items",
                    list: true,
                    ui: { itemProps: (item) => ({ label: item?.title ?? "Feature" }) },
                    fields: [
                      { type: "string", name: "title", label: "Title" },
                      { type: "string", name: "description", label: "Description", ui: { component: "textarea" } },
                    ],
                  },
                ],
              },
              {
                name: "cta",
                label: "Call to Action",
                fields: [
                  { type: "string", name: "heading", label: "Heading" },
                  { type: "string", name: "body", label: "Body", ui: { component: "textarea" } },
                  { type: "string", name: "buttonText", label: "Button Text" },
                ],
              },
            ],
          },
        ],
      },
    ],
  },
});
