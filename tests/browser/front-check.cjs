// Regressão do contrato de paginação e dos formulários; API inteiramente sintética.
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.GL_BASE_URL || 'http://localhost:5401';
const paginated = (items = [], total = items.length, page = 1, perPage = 2) => ({
  items,
  pagination: { total, page, per_page: perPage, total_pages: Math.ceil(total / perPage), has_next_page: page * perPage < total, has_previous_page: page > 1 }
});
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox'] });
  try {
    const page = await browser.newPage();
    page.setDefaultTimeout(15000);
    page.setDefaultNavigationTimeout(15000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const user = { id: 1, nome: 'Operador de teste', urole: 'admin', status: true, unidades: [{ id: 1, nome: 'Belo Horizonte', sigla: 'BH', ativa: true }] };
    const person = { id: 1, nome: 'Pessoa de teste', cpf: '529.982.247-25', celular: '(31) 99999-9999', email: '', data_nascimento: '1990-01-01', estado_civil: 'solteiro', como_conheceu: 'conhec', procurou_outro_local: 'nao', pj_constituida: 'nao', status: 1, endereco: { logradouro: 'Rua de teste', numero: '10', bairro: 'Centro', cep: '30130-000', cidade: 'Belo Horizonte', estado: 'MG' } };
    const cases = [1, 2, 3].map(id => ({ id, descricao: `Caso de teste ${id}`, area_direito: 'civel', sub_area: 'familia', situacao_deferimento: 'ativo', status: true, usuario_responsavel: user, estagiario: null, clientes: [person], data_criacao: '2026-01-01' }));
    let rejectLogin = true;
    const writes = [];
    await page.route('**/api/**', async route => {
      const request = route.request();
      const url = new URL(request.url());
      const path = url.pathname;
      let data = paginated();
      if (path === '/api/auth/login') {
        assert.equal(request.headers()['content-type'], 'application/json');
        if (rejectLogin) return route.fulfill({ status: 401, json: { success: false, error: { message: 'Login inválido' } } });
        data = { token: 'fixture-sem-acesso-real', user };
      } else if (path === '/api/user/me') data = user;
      else if (path === '/api/user/opcoes') data = { items: [user] };
      else if (path === '/api/auth/setup-status') data = { needs_setup: false };
      else if (path === '/api/caso') {
        const number = Number(url.searchParams.get('page') || 1);
        data = paginated(cases.slice((number - 1) * 2, number * 2), 3, number);
      } else if (path === '/api/atendido/1') {
        if (request.method() === 'PUT') { writes.push(request.postDataJSON()); Object.assign(person, writes.at(-1)); }
        data = person;
      } else if (path === '/api/atendido') data = paginated([person]);
      else if (request.method() !== 'GET') throw new Error(`Gravação inesperada: ${request.method()} ${path}`);
      await route.fulfill({ json: { success: true, data } });
    });
    await page.goto(base + '/login?redirectTo=%2Fcasos');
    await page.getByLabel('Email', { exact: true }).fill('teste@example.test');
    await page.getByLabel('Senha', { exact: true }).fill('senha-teste');
    await page.getByRole('button', { name: 'Entrar', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: 'E-mail ou senha incorretos' }).waitFor();
    rejectLogin = false;
    await page.getByRole('button', { name: 'Entrar', exact: true }).click();
    await page.waitForURL('**/casos');
    await page.getByText('Página 1 de 2', { exact: true }).waitFor();
    assert.equal(await page.getByTitle('Primeira página', { exact: true }).isDisabled(), true);
    await page.getByTitle('Próxima página', { exact: true }).click();
    await page.waitForURL(url => url.pathname === '/casos' && url.searchParams.get('page') === '2');
    await page.getByText('Página 2 de 2', { exact: true }).waitFor();
    await page.getByRole('cell', { name: '3', exact: true }).waitFor();
    assert.equal(await page.locator('tbody tr').count(), 1);
    assert.equal(await page.getByTitle('Próxima página', { exact: true }).isDisabled(), true);
    await page.goto(base + '/plantao/atendidos-assistidos');
    await page.goBack();
    await page.getByText('Página 2 de 2', { exact: true }).waitFor();
    await page.goto(base + '/plantao/atendidos-assistidos/1/editar');
    await page.getByLabel('Nome Completo', { exact: true }).waitFor();
    assert.equal(await page.getByLabel('Logradouro', { exact: true }).inputValue(), 'Rua de teste');
    await page.getByLabel('Logradouro', { exact: true }).fill('Rua corrigida');
    await page.getByRole('button', { name: 'Salvar Alterações', exact: true }).first().click();
    await page.waitForURL('**/plantao/atendidos-assistidos/1');
    assert.equal(writes.length, 1);
    assert.equal(writes[0].logradouro, 'Rua corrigida');
    assert.equal(writes[0].data_nascimento, '1990-01-01');
    assert.deepEqual(errors, []);
    console.log('OK: login rejeitado e aceito, paginação, voltar no histórico e edição de atendido.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
