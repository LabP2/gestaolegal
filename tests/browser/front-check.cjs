// Regressão do contrato de paginação e dos formulários; API inteiramente sintética.
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.GL_BASE_URL || 'http://localhost:5401';
const paginated = (items = [], total = items.length, page = 1, perPage = 2) => ({
  items,
  total, page, per_page: perPage, total_pages: Math.ceil(total / perPage), has_next_page: page * perPage < total, has_previous_page: page > 1
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
    const arquivo = { id: 7, titulo: 'Arquivo de teste', nome: 'teste.txt', descricao: 'Conteúdo sintético' };
    const caso = { ...cases[0], id_usuario_responsavel: 1, situacao_deferimento: 'deferido', id_orientador: null, id_estagiario: null, id_colaborador: null, processos: [], arquivos: [] };
    const orientacao = { id: 1, area_direito: 'penal', descricao: 'Orientação de teste', atendidos: [person], status: true };
    const assistencia = { id: 1, nome: 'Parceiro de teste', regiao: 'centro_sul', areas_atendidas: ['civel'], telefone: '(31) 3333-3333', email: 'parceiro@example.test', endereco: person.endereco, orientacoes: [], status: true };
    const edits = {};
    let upload = null;
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
      else if (path === '/api/auth/needs-setup') data = { needs_setup: false };
      else if (path === '/api/caso') {
        const number = Number(url.searchParams.get('page') || 1);
        data = paginated(cases.slice((number - 1) * 2, number * 2), 3, number);
      } else if (['/api/caso/1', '/api/orientacao_juridica/1', '/api/assistencia_judiciaria/1'].includes(path)) {
        data = { '/api/caso/1': caso, '/api/orientacao_juridica/1': orientacao, '/api/assistencia_judiciaria/1': assistencia }[path];
        if (request.method() === 'PUT') { edits[path] = request.postDataJSON(); Object.assign(data, edits[path]); }
      } else if (path.endsWith('/lembretes')) data = [];
      else if (path === '/api/atendido/1') {
        if (request.method() === 'PUT') { writes.push(request.postDataJSON()); Object.assign(person, writes.at(-1)); }
        data = person;
      } else if (path === '/api/atendido') data = paginated([person]);
      else if (path === '/api/arquivo/' && request.method() === 'POST') {
        upload = request.postData();
        assert.match(request.headers()['content-type'], /^multipart\/form-data; boundary=/);
        data = arquivo;
      } else if (path === '/api/arquivo/7') data = arquivo;
      else if (path === '/api/arquivo/7/download') return route.fulfill({ contentType: 'text/plain', body: 'conteudo-sintetico', headers: { 'content-disposition': 'attachment; filename=teste.txt' } });
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
    await page.goto(base + '/casos/1/editar');
    await page.getByLabel('Descrição', { exact: true }).fill('Descrição atualizada do caso');
    await page.getByRole('button', { name: 'Salvar Alterações', exact: true }).click();
    await page.waitForURL('**/casos/1');
    assert.equal(edits['/api/caso/1'].situacao_deferimento, 'ativo', 'Situação legada deve permanecer normalizada');
    assert.equal(edits['/api/caso/1'].descricao, 'Descrição atualizada do caso');
    await page.goto(base + '/plantao/orientacoes-juridicas/1/editar');
    await page.getByLabel('Descrição', { exact: true }).fill('Orientação jurídica atualizada');
    await page.getByRole('button', { name: 'Salvar Alterações', exact: true }).click();
    await page.waitForURL('**/plantao/orientacoes-juridicas/1');
    assert.equal(edits['/api/orientacao_juridica/1'].descricao, 'Orientação jurídica atualizada');
    assert.deepEqual(edits['/api/orientacao_juridica/1'].atendidos_ids, [1]);
    await page.goto(base + '/plantao/assistencias-judiciarias/1/editar');
    await page.getByLabel('Nome', { exact: true }).fill('Parceiro atualizado');
    await page.getByRole('button', { name: 'Salvar Alterações', exact: true }).click();
    await page.waitForURL('**/plantao/assistencias-judiciarias/1');
    assert.equal(edits['/api/assistencia_judiciaria/1'].nome, 'Parceiro atualizado');
    assert.deepEqual(edits['/api/assistencia_judiciaria/1'].areas_atendidas, ['civel']);
    await page.goto(base + '/arquivos/cadastrar-arquivo');
    await page.getByLabel('Título *', { exact: true }).fill(arquivo.titulo);
    await page.getByLabel('Descrição', { exact: true }).fill(arquivo.descricao);
    await page.locator('input[type=file]').setInputFiles({ name: 'teste.txt', mimeType: 'text/plain', buffer: Buffer.from('conteudo-sintetico') });
    await page.getByRole('button', { name: 'Cadastrar', exact: true }).click();
    await page.waitForURL('**/arquivos/7');
    assert.match(upload, /name="titulo"/);
    assert.match(upload, /Arquivo de teste/);
    assert.match(upload, /filename="teste.txt"/);
    assert.match(upload, /conteudo-sintetico/);
    const downloaded = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Baixar', exact: true }).click();
    const download = await downloaded;
    assert.equal(download.suggestedFilename(), 'teste.txt');
    assert.equal(await download.failure(), null);
    assert.deepEqual(errors, []);
    console.log('OK: login rejeitado e aceito, paginação, voltar no histórico, edição de atendido/caso/orientação/assistência, upload e download.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
