import toc from "remark-toc";
import slug from "remark-slug";
import gfm from "remark-gfm";

export default {
  plugins: [
    [gfm, {}],
    [slug, {}],
    [
      toc,
      {
        heading: "目次",
        maxDepth: 2
      }
    ]
  ]
};
