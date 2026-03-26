import type { SiteConfig } from '@mcptoolshop/site-theme';

export const config: SiteConfig = {
  title: 'Sprite Foundry',
  description: 'Headless sprite generation pipeline — ComfyUI + SQLite + Godot finish lab',
  logoBadge: 'SF',
  brandName: 'Sprite Foundry',
  repoUrl: 'https://github.com/mcp-tool-shop-org/sprite-foundry',
  footerText: 'MIT Licensed — built by <a href="https://github.com/mcp-tool-shop-org" style="color:var(--color-muted);text-decoration:underline">MCP Tool Shop</a>',

  hero: {
    badge: 'Python CLI',
    headline: 'Sprite Foundry',
    headlineAccent: 'for Star Freight.',
    description: 'Generate, review, and export 8-direction pixel sprites with normal and depth maps — all from a single CLI.',
    primaryCta: { href: '#usage', label: 'Get started' },
    secondaryCta: { href: '#features', label: 'See the pipeline' },
    previews: [
      { label: 'Clone', code: 'git clone https://github.com/mcp-tool-shop-org/sprite-foundry.git' },
      { label: 'Init', code: 'python -m foundry init' },
      { label: 'Export', code: 'python -m foundry export <run_id>' },
    ],
  },

  sections: [
    {
      kind: 'features',
      id: 'features',
      title: 'Pipeline',
      subtitle: 'Five stages from concept to game-ready sprite pack.',
      features: [
        { title: 'ComfyUI Generation', desc: 'SDXL + pixel-art-xl LoRA + ControlNet (Depth + Canny). 8 directions per subject with morphology variants for non-humanoid body plans.' },
        { title: 'SQLite Registry', desc: 'Append-only lifecycle tracking with 13 states, reject codes, regen lineage, and full provenance — every decision is auditable.' },
        { title: 'Godot Finish Lab', desc: '4 lighting states × 8 directions = 32 captures per subject. Normal maps verified under moonlight, torchlight, and particle effects.' },
        { title: 'Deterministic Export', desc: 'SHA-256 checksums, frozen contract v1.0.0, manifest.json with provenance. Consumers validate schema before loading.' },
        { title: '20 Production Packs', desc: '7 crew, 6 creature, 3 hostile, 2 authority, 2 civilian — all finish-accepted with zero contract violations.' },
        { title: 'Morphology System', desc: 'Arthropod, quadruped, and winged body families via depth/edge reference images for non-standard character shapes.' },
      ],
    },
    {
      kind: 'code-cards',
      id: 'usage',
      title: 'Usage',
      cards: [
        {
          title: 'Register a subject',
          code: 'python -m foundry subject-add sera_vale "Sera Vale" \\\n  --role crew --consumer star-freight',
        },
        {
          title: 'Review and export',
          code: '# Check pipeline status\npython -m foundry status\n\n# Accept a finished run\npython -m foundry batch-accept <run_id>\n\n# Export to deterministic pack\npython -m foundry export <run_id>',
        },
        {
          title: 'Export contract (frozen)',
          code: 'exports/{subject_slug}/{run_id}/\n├── albedo/    8 × 48px transparent PNGs\n├── normal/    8 × matching normal maps\n├── depth/     8 × matching depth maps\n├── preview/   contact sheet\n└── manifest.json  (SHA-256, provenance)',
        },
      ],
    },
  ],
};
