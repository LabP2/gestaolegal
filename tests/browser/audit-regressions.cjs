// Regressões encontradas na auditoria manual da WT. A API é sintética.
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.GL_BASE_URL || 'http://localhost:5402';
const paginated = (items) => ({ items, total: items.length, page: 1, per_page: 50, total_pages: 1 });
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox'] });
  try {
    const page = await browser.newPage();
    page.setDefaultTimeout(10000);
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    const user = { id: 1, nome: 'Operador', email: 'operador@example.test', urole: 'admin', status: true, unidades: [{ id: 1, nome: 'Belo Horizonte', sigla: 'BH', ativa: true }] };
    const person = { id: 1, nome: 'Pessoa inativa', status: false, is_assistido: true, cpf: '529.982.247-25' };
    const processos = [
      { id: 10, especie: 'Ação', numero: '0000000-00.2026.8.13.0000', vara: 'Vara original', identificacao: 'Primeiro processo', obs: 'Preservar observação', status: true, data_distribuicao: 'Mon, 15 Jan 2024 00:00:00 GMT', valor_causa_inicial: 1234.56 },
      { id: 11, especie: 'Recurso', numero: '2222222', vara: 'Outra vara', status: true },
      { id: 12, especie: 'Ação', numero: 'INATIVO', status: false }
    ];
    const caso = { id: 1, descricao: 'Caso de regressão', area_direito: 'ambiental', situacao_deferimento: 'ativo', status: true, processos, clientes: [], arquivos: [], usuario_responsavel: user };
    let saved;
    let restored = 0;
    await page.route('**/api/**', async route => {
      const request = route.request();
      const path = new URL(request.url()).pathname.replace(/\/$/, '');
      let data = paginated([]);
      if (path === '/api/auth/login') data = { token: 'fixture-sem-acesso-real', user };
      else if (path === '/api/auth/needs-setup') data = { needs_setup: false };
      else if (path === '/api/user/me') data = user;
      else if (path === '/api/caso/1') data = caso;
      else if (path === '/api/caso/1/lembretes') data = [];
      else if (path === '/api/atendido') data = paginated([person]);
      else if (path === '/api/atendido/1/reativar' && request.method() === 'POST') {
        restored++; person.status = true; data = person;
      } else if (path === '/api/caso/1/processos/10' && request.method() === 'PUT') {
        saved = request.postDataJSON(); Object.assign(processos[0], saved); data = processos[0];
      } else if (path === '/api/caso/1/processos/10' && request.method() === 'DELETE') {
        processos[0].status = false; data = {};
      } else if (request.method() !== 'GET') throw new Error(`Gravação inesperada: ${request.method()} ${path}`);
      await route.fulfill({ json: { success: true, data } });
    });
    await page.goto(base + '/login?redirectTo=%2Fcasos%2F1');
    await page.getByLabel('Email', { exact: true }).fill('operador@example.test');
    await page.getByLabel('Senha', { exact: true }).fill('senha-fixture');
    await page.getByRole('button', { name: 'Entrar', exact: true }).click();
    await page.waitForURL('**/casos/1');
    const first = () => page.getByText('Ação · Nº 0000000-00.2026.8.13.0000', { exact: true });
    await first().waitFor();
    assert.equal(await page.getByText('Ação · Nº INATIVO', { exact: true }).count(), 0);
    await first().locator('../../..').getByTitle('Editar', { exact: true }).click();
    await page.getByRole('dialog').waitFor();
    assert.equal(await page.locator('input[name=numero]').inputValue(), processos[0].numero);
    assert.equal(await page.locator('input[name=vara]').inputValue(), 'Vara original');
    assert.equal(await page.locator('[name=data_distribuicao]').inputValue(), '2024-01-15');
    await page.locator('input[name=vara]').fill('Vara corrigida');
    await page.getByRole('button', { name: 'Salvar Alterações', exact: true }).click();
    await page.getByRole('dialog').waitFor({ state: 'hidden' });
    assert.equal(saved.numero, '0000000-00.2026.8.13.0000');
    assert.equal(saved.obs, 'Preservar observação');
    assert.equal(saved.valor_causa_inicial, 1234.56);
    assert.equal(saved.vara, 'Vara corrigida');
    await page.reload();
    await first().waitFor();
    await page.getByText('Recurso · Nº 2222222', { exact: true }).locator('../../..').getByTitle('Editar', { exact: true }).click();
    assert.equal(await page.locator('input[name=numero]').inputValue(), '2222222');
    await page.getByRole('button', { name: 'Cancelar', exact: true }).click();
    await page.getByRole('button', { name: 'Novo Processo', exact: true }).click();
    assert.equal(await page.locator('input[name=numero]').inputValue(), '');
    await page.getByRole('button', { name: 'Cancelar', exact: true }).click();
    await first().locator('../../..').locator('button').last().click();
    await page.getByRole('alertdialog').getByRole('button', { name: 'Inativar', exact: true }).click();
    await first().waitFor({ state: 'hidden' });
    await page.reload();
    await page.getByRole('button', { name: 'Novo Processo', exact: true }).waitFor();
    assert.equal(await first().count(), 0);
    await page.goto(base + '/plantao/atendidos-assistidos?show_inactive=true');
    await page.getByRole('row').filter({ hasText: person.nome }).getByTitle('Reativar', { exact: true }).click();
    await page.getByRole('row').filter({ hasText: person.nome }).getByText('Ativo', { exact: true }).waitFor();
    assert.equal(restored, 1);
    await page.reload();
    await page.getByRole('row').filter({ hasText: person.nome }).getByText('Ativo', { exact: true }).waitFor();
    const breadcrumb = page.locator('nav[aria-label=breadcrumb]').getByRole('link', { name: 'Plantão', exact: true });
    assert.equal(await breadcrumb.getAttribute('href'), '/plantao/escalas');
    await breadcrumb.click();
    await page.waitForURL('**/plantao/escalas');
    await page.getByRole('link', { name: 'Nova escala', exact: true }).waitFor();
    assert.deepEqual(errors, []);
    console.log('OK: edição/reabertura/criação de processo, preservação de dados, inativação após reload, reativação de atendido e breadcrumb.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
