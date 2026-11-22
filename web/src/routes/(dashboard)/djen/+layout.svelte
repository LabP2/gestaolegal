<script lang="ts">
	import AvisoDjenDemo from '#lib/components/djen/aviso-djen-demo.svelte';

	let { children } = $props();
</script>

<!-- Só aparece com DEMO_MODE na API (GET /api/ambiente). -->
<div class="mb-2 empty:hidden"><AvisoDjenDemo /></div>
{@render children?.()}
