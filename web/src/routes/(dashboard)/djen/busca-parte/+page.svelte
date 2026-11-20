<script lang="ts">
	import BuscaParte from '#lib/components/djen/busca-parte.svelte';
	import type { PageProps } from './$types';
	let { data }: PageProps = $props();
</script>

<BuscaParte {data} />
