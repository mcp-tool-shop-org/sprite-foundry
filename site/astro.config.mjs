// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

import tailwindcss from '@tailwindcss/vite';

// https://astro.build/config
export default defineConfig({
  site: 'https://mcp-tool-shop-org.github.io',
  base: '/sprite-foundry',
  integrations: [
    starlight({
      title: 'Sprite Foundry',
      social: [
        { icon: 'github', label: 'GitHub', href: 'https://github.com/mcp-tool-shop-org/sprite-foundry' },
      ],
      sidebar: [
        {
          label: 'Handbook',
          items: [
            { label: 'Overview', slug: 'handbook' },
            { label: 'Getting Started', slug: 'handbook/getting-started' },
            { label: 'Pipeline', slug: 'handbook/pipeline' },
            { label: 'CLI Reference', slug: 'handbook/reference' },
            { label: 'Security', slug: 'handbook/security' },
          ],
        },
      ],
      customCss: ['./src/styles/starlight-custom.css'],
      disable404Route: true,
    }),
  ],
  vite: {
    plugins: [tailwindcss()]
  }
});
