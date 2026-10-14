import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export const base = '/docs/xy';
const publicURL = process.env.XY_DOCS_PUBLIC_URL?.trim().replace(/\/+$/, '');
if (publicURL) {
  const url = new URL(publicURL);
  if (url.protocol !== 'https:' || url.search || url.hash || url.pathname.replace(/\/+$/, '') !== base) {
    throw new Error('XY_DOCS_PUBLIC_URL must be an owned HTTPS URL ending in /docs/xy, without query or fragment');
  }
}
export default defineConfig({
  site: publicURL ? new URL(publicURL).origin : undefined,
  base,
  trailingSlash: 'always',
  output: 'static',
  outDir: './dist',
  integrations: [starlight({
    title: 'XYG',
    description: 'Graph visualization and charting for Python, Node.js, and browser WebAssembly. Built for GraphForge.',
    logo: { src: './src/assets/xyg.svg', replacesTitle: true },
    social: [
      { icon: 'github', label: 'XYG on GitHub', href: 'https://github.com/CurateLabs/xyg' },
    ],
    editLink: { baseUrl: 'https://github.com/CurateLabs/xyg/edit/main/docs/' },
    customCss: ['./src/styles/custom.css'],
    components: { Head: './src/components/Head.astro', Footer: './src/components/Footer.astro' },
    sidebar: [
      { label: 'What is XYG?', slug: 'index' },
      { label: 'Use with GraphForge', slug: 'integrations/graphforge' },
      { label: 'Rust core and host parity', slug: 'core-concepts/rust-engine-and-host-parity' },
      { label: 'Get started', items: [{ autogenerate: { directory: 'overview' } }] },
      { label: 'Graphs and charts', items: [{ autogenerate: { directory: 'charts' } }] },
      { label: 'Core concepts', items: [{ autogenerate: { directory: 'core-concepts' } }] },
      { label: 'Styling', items: [{ autogenerate: { directory: 'styling' } }] },
      { label: 'Components', items: [{ autogenerate: { directory: 'components' } }] },
      { label: 'Integrations', items: [{ autogenerate: { directory: 'integrations' } }] },
      { label: 'Guides', items: [{ autogenerate: { directory: 'guides' } }] },
      { label: 'Advanced', items: [{ autogenerate: { directory: 'advanced' } }] },
      { label: 'API reference', items: [{ autogenerate: { directory: 'api-reference' } }] },
    ],
  })],
  redirects: {
    '/charts/annotations/': '/docs/xy/components/annotations/',
    '/core-concepts/animations/': '/docs/xy/styling/animations/',
    '/styling/playground/': '/docs/xy/styling/examples/#author-a-palette',
    '/styling/recipes/': '/docs/xy/styling/examples/#responsive-combo-chart',
    '/styling/mark-styles/': '/docs/xy/styling/customize/#fill-stroke-opacity-and-gradients',
    '/styling/component-variations/': '/docs/xy/styling/customize/#annotations',
    '/integrations/reflex/': '/docs/xy/integrations/graphforge/',
  },
});
