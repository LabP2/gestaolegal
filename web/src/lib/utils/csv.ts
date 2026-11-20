/** CSV para planilhas em português, com proteção contra fórmulas em dados externos. */
export function gerarCsv(linhas: (string | number | null | undefined)[][]): string {
	return (
		'\uFEFF' +
		linhas
			.map((linha) =>
				linha
					.map((valor) => {
						let texto = String(valor ?? '');
						if (/^[\s\uFEFF]*[=+@-]/u.test(texto) || /^[\t\r\n]/.test(texto)) texto = `'${texto}`;
						return `"${texto.replaceAll('"', '""')}"`;
					})
					.join(';')
			)
			.join('\r\n') +
		'\r\n'
	);
}
