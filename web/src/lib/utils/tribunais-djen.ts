// Tribunais aceitos pelo DJEN (comunicaapi.pje.jus.br/api/v1/comunicacao/tribunal,
// consultado em 09/11/2026). Lista fixa: muda raramente e evita uma chamada a
// mais à API. Minas Gerais e os nacionais primeiro; o TRF de cada região aparece
// uma vez só.
export const TRIBUNAIS_DJEN: { grupo: string; siglas: string[] }[] = [
	{ grupo: 'Minas Gerais', siglas: ['TRF6', 'TJMG', 'TRT3', 'TRE-MG', 'TJMMG', 'TRF1'] },
	{ grupo: 'Nacionais', siglas: ['STJ', 'TST', 'TSE', 'STM', 'CJF', 'CNJ', 'SEEU', 'PJeCor'] },
	{ grupo: 'Federais (TRF)', siglas: ['TRF2', 'TRF3', 'TRF4', 'TRF5'] },
	{
		grupo: 'Estaduais (TJ)',
		siglas: [
			'TJAC',
			'TJAL',
			'TJAM',
			'TJAP',
			'TJBA',
			'TJCE',
			'TJDFT',
			'TJES',
			'TJGO',
			'TJMA',
			'TJMS',
			'TJMT',
			'TJPA',
			'TJPB',
			'TJPE',
			'TJPI',
			'TJPR',
			'TJRJ',
			'TJRN',
			'TJRO',
			'TJRR',
			'TJRS',
			'TJSC',
			'TJSE',
			'TJSP',
			'TJTO',
			'TJMRS',
			'TJMSP'
		]
	},
	{
		grupo: 'Trabalho (TRT)',
		siglas: Array.from({ length: 24 }, (_, i) => `TRT${i + 1}`).filter((s) => s !== 'TRT3')
	},
	{
		grupo: 'Eleitorais (TRE)',
		siglas: [
			'TRE-AC',
			'TRE-AL',
			'TRE-AM',
			'TRE-AP',
			'TRE-BA',
			'TRE-CE',
			'TRE-DF',
			'TRE-ES',
			'TRE-GO',
			'TRE-MA',
			'TRE-MS',
			'TRE-MT',
			'TRE-PA',
			'TRE-PE',
			'TRE-PI',
			'TRE-PR',
			'TRE-RJ',
			'TRE-RN',
			'TRE-RO',
			'TRE-RS',
			'TRE-SC',
			'TRE-SE',
			'TRE-SP',
			'TRE-TO'
		]
	}
];

export const MAX_TRIBUNAIS = 10;
