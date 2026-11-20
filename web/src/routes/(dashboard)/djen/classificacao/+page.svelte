<script lang="ts">
	import Acervo from '#lib/components/djen/acervo.svelte';
	import type { PageProps } from './$types';
	let { data }: PageProps = $props();
</script>

<Acervo dados={data.acervo} treino />
