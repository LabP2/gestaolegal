<script lang="ts">
	import NavMain from './nav-main.svelte';
	import NavUser from './nav-user.svelte';
	import * as Sidebar from '$lib/components/ui/sidebar/index.js';
	import type { ComponentProps } from 'svelte';
	import CompanyLogo from './company-logo.svelte';
	import type { Me } from '$lib/types';
	import { podeVer, type ItemComPapeis } from '$lib/utils/permissoes';
	import UsersIcon from '@lucide/svelte/icons/users';
	import ClockIcon from '@lucide/svelte/icons/clock';
	import FileTextIcon from '@lucide/svelte/icons/file-text';
	import ChartBarIcon from '@lucide/svelte/icons/bar-chart-3';
	import FolderIcon from '@lucide/svelte/icons/folder';
	import BellIcon from '@lucide/svelte/icons/bell';
	import BuildingIcon from '@lucide/svelte/icons/building-2';
	import NewspaperIcon from '@lucide/svelte/icons/newspaper';

	type NavItem = ItemComPapeis & {
		title: string;
		url: string;
		/** Só aparece com o DJEN ligado para o NPJ (`tenant.djen_ativo`). */
		djen?: boolean;
	};

	const baseNavMain: (NavItem & { icon: unknown; isActive?: boolean; items: NavItem[] })[] = [
		{
			title: 'Gestão de Usuários',
			url: '/usuarios',
			icon: UsersIcon,
			isActive: true,
			roles: ['admin'],
			items: []
		},
		{
			title: 'Plantão',
			url: '/plantao',
			icon: ClockIcon,
			items: [
				{
					title: 'Escalas de Plantão',
					url: '/plantao/escalas'
				},
				{
					title: 'Registro de Presença',
					url: '/plantao/registro-presenca'
				},
				{
					title: 'Confirmar Presença',
					url: '/plantao/confirmar-presenca',
					roles: ['admin', 'colab_proj', 'prof']
				},
				{
					title: 'Atendidos e Assistidos',
					url: '/plantao/atendidos-assistidos'
				},
				{
					title: 'Fila de atendimento',
					url: '/plantao/fila-atendimento'
				},
				{
					title: 'Orientações Jurídicas',
					url: '/plantao/orientacoes-juridicas'
				},
				{
					title: 'Assistências Judiciárias',
					url: '/plantao/assistencias-judiciarias'
				}
			]
		},
		{
			title: 'Casos',
			url: '/casos',
			icon: FileTextIcon,
			items: [
				{
					title: 'Cadastrar Novo Caso',
					url: '/casos/cadastrar-novo-caso'
				},
				{
					title: 'Meus Casos',
					url: '/casos?participante=me'
				},
				{
					title: 'Gestão de Casos',
					url: '/casos'
				},
				{
					title: 'Links de Roteiro',
					url: '/casos/links-roteiro'
				}
			]
		},
		{
			title: 'Arquivos',
			url: '/arquivos',
			icon: FolderIcon,
			items: [
				{
					title: 'Cadastrar Arquivo',
					url: '/arquivos/cadastrar-arquivo',
					roles: ['admin', 'prof', 'colab_proj', 'colab_ext']
				},
				{
					title: 'Ver Arquivos',
					url: '/arquivos'
				}
			]
		},
		{
			title: 'DJEN',
			url: '/djen',
			icon: NewspaperIcon,
			djen: true,
			items: [
				{
					title: 'Publicações',
					url: '/djen'
				},
				{
					title: 'Sem caso',
					url: '/djen/sem-caso',
					roles: ['admin', 'prof', 'orient']
				},
				{
					title: 'OABs monitoradas',
					url: '/djen/oabs',
					roles: ['admin']
				}
			]
		},
		{
			title: 'Notificações',
			url: '/notificacoes',
			icon: BellIcon,
			items: []
		},
		{
			title: 'Unidades',
			url: '/unidades',
			icon: BuildingIcon,
			roles: ['admin'],
			items: []
		},
		{
			title: 'Relatórios',
			url: '/relatorios',
			icon: ChartBarIcon,
			roles: ['admin', 'orient', 'colab_ext'],
			items: []
		}
	];

	let {
		ref = $bindable(null),
		collapsible = 'icon',
		user,
		...restProps
	}: ComponentProps<typeof Sidebar.Root> & { user: Me } = $props();

	const djenAtivo = $derived(user.tenant?.djen_ativo === true);
	const visivel = (item: NavItem) => podeVer(item, user.urole) && (!item.djen || djenAtivo);

	let navMainItems = $derived(
		baseNavMain.filter(visivel).map((item) => ({
			...item,
			items: item.items.filter(visivel)
		}))
	);

	let formattedUser = $derived({
		nome: user.nome,
		email: user.email
	});
</script>

<Sidebar.Root {collapsible} {...restProps}>
	<Sidebar.Header>
		<CompanyLogo />
	</Sidebar.Header>
	<Sidebar.Content>
		<NavMain items={navMainItems} />
	</Sidebar.Content>
	<Sidebar.Footer>
		<a
			href="/termos-de-uso"
			class="px-2 text-xs text-muted-foreground group-data-[collapsible=icon]:hidden hover:underline"
		>
			Termos de uso
		</a>
		<NavUser user={formattedUser} />
	</Sidebar.Footer>
	<Sidebar.Rail />
</Sidebar.Root>
