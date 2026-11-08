/** Telas acessíveis sem estar autenticado. */
// `/plataforma` tem sessão própria (cookie `plataforma_token`), conferida no
// layout dela; para o sistema do NPJ, ela é pública.
const ROTAS_PUBLICAS = ['/login', '/esqueci-a-senha', '/redefinir-senha', '/plataforma'];

/** Se a rota dispensa sessão (o prefixo cobre /redefinir-senha/<token>). */
export function ehRotaPublica(pathname: string): boolean {
	return ROTAS_PUBLICAS.some((rota) => pathname === rota || pathname.startsWith(`${rota}/`));
}
