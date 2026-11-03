// Regressão da issue #114; todas as chamadas de API usam dados sintéticos.
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.GL_BASE_URL || 'http://localhost:5002';
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox'] });
  try {
    const ctx = await browser.newContext();
    await ctx.addCookies([{ name: 'auth_token', value: 'fixture-sem-acesso-real', url: base }]);
    await ctx.addInitScript(() => localStorage.setItem('unidade_ativa', '1'));
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const assistido = {
      sexo: 'M', profissao: 'Engenheiro', raca: 'parda', rg: '12.345.678', grau_instrucao: 'superior_comp',
      salario: 2000, beneficio: 'nao', contribui_inss: 'sim', qtd_pessoas_moradia: 4, renda_familiar: 5000,
      participacao_renda: 'principal', tipo_moradia: 'propria_quitada', possui_outros_imoveis: false,
      possui_veiculos: false, doenca_grave_familia: 'nao',
      assistido_pessoa_juridica: { enquadramento: 'outros', especificacao_enquadramento: 'Associação', socios: ['Ana', 'João'], situacao_receita: 'Ativa' }
    };
    const pessoa = {
      id: 1, nome: 'Pessoa sintética', cpf: '123.456.789-00', celular: '(31) 99999-9999', email: '',
      data_nascimento: '1990-01-01', estado_civil: 'solteiro', como_conheceu: 'internet',
      procurou_outro_local: 'nao', pj_constituida: 'sim', repres_legal: true, status: 1, assistido
    };
    const writes = [];
    await page.route('**/api/**', async route => {
      const url = new URL(route.request().url());
      let data = { items: [], total: 0, total_pages: 0 };
      if (url.pathname.endsWith('/user/me')) data = { id: 1, nome: 'Operador sintético', urole: 'admin', status: true, unidades: [{ id: 1, nome: 'Belo Horizonte', sigla: 'BH', ativa: true }] };
      else if (/\/atendido\/1$/.test(url.pathname)) data = pessoa;
      else if (/\/atendido\/1\/assistido$/.test(url.pathname)) {
        assert.equal(route.request().method(), 'PUT');
        const body = route.request().postDataJSON();
        writes.push(body);
        pessoa.assistido = { ...assistido, ...body };
        data = pessoa;
      } else assert.equal(route.request().method(), 'GET', 'Toda escrita deve ser interceptada explicitamente');
      await route.fulfill({ json: { success: true, data } });
    });
    const choose = async label => {
      await page.getByLabel('Enquadramento', { exact: true }).click();
      await page.getByRole('option', { name: label, exact: true }).click();
    };
    const root = base + '/plantao/atendidos-assistidos/1';
    await page.goto(root + '/editar');
    await page.getByLabel('Qual o nome do sócio 2?', { exact: true }).waitFor();
    assert.equal(await page.getByLabel('Qual o nome do sócio 1?', { exact: true }).inputValue(), 'Ana');
    assert.equal(await page.getByLabel('Especifique o enquadramento da PJ', { exact: true }).inputValue(), 'Associação');
    await page.getByLabel('Especifique o enquadramento da PJ', { exact: true }).fill('   ');
    await page.getByRole('button', { name: 'Salvar Alterações', exact: true }).last().click();
    await page.getByText('Especifique o enquadramento da PJ', { exact: true }).nth(1).waitFor();
    assert.equal(writes.length, 0, 'Outros sem especificação não deve ser enviado');
    await page.getByLabel('Especifique o enquadramento da PJ', { exact: true }).fill('Associação');
    await page.getByLabel('Quantos sócios tem a Pessoa Jurídica?', { exact: true }).fill('3');
    await page.getByLabel('Quantos sócios tem a Pessoa Jurídica?', { exact: true }).press('Tab');
    await page.getByLabel('Qual o nome do sócio 3?', { exact: true }).fill('Maria');
    await page.getByLabel('Quantos sócios tem a Pessoa Jurídica?', { exact: true }).fill('2');
    assert.equal(await page.getByLabel('Qual o nome do sócio 3?', { exact: true }).count(), 0);
    assert.equal(await page.getByLabel('Qual o nome do sócio 1?', { exact: true }).inputValue(), 'Ana');
    await choose('Microempreendedor Individual');
    assert.equal(await page.getByLabel('Quantos sócios tem a Pessoa Jurídica?', { exact: true }).count(), 0);
    assert.equal(await page.getByLabel('Especifique o enquadramento da PJ', { exact: true }).count(), 0);
    await page.getByRole('button', { name: 'Salvar Alterações', exact: true }).last().click();
    await page.waitForFunction(() => location.pathname === '/plantao/atendidos-assistidos');
    assert.equal(writes.length, 1);
    assert.equal(writes[0].assistido_pessoa_juridica.enquadramento, 'mei');
    assert.deepEqual(writes[0].assistido_pessoa_juridica.socios, []);
    assert.equal(writes[0].assistido_pessoa_juridica.especificacao_enquadramento, null);
    await page.goto(root);
    await page.getByText('Microempreendedor Individual', { exact: true }).waitFor();
    assert.equal(await page.getByText(/Sócios da Pessoa Jurídica/).count(), 0);
    await page.goto(root + '/editar');
    await choose('Microempresa');
    const name = page.getByLabel('Qual o nome do sócio 1?', { exact: true });
    await name.waitFor();
    assert.equal(await name.inputValue(), '');
    await name.fill('Maria');
    await page.getByRole('button', { name: 'Salvar Alterações', exact: true }).last().click();
    await page.waitForFunction(() => location.pathname === '/plantao/atendidos-assistidos');
    assert.equal(writes.length, 2);
    assert.deepEqual(writes[1].assistido_pessoa_juridica.socios, ['Maria']);
    await page.goto(root);
    await page.getByText('Sócios da Pessoa Jurídica (1)', { exact: true }).waitFor();
    const texto = await page.getByText('Dados Jurídicos', { exact: true }).locator('..').locator('..').innerText();
    assert(texto.indexOf('Enquadramento') < texto.indexOf('Sócios da Pessoa Jurídica'));
    assert(texto.indexOf('Sócios da Pessoa Jurídica') < texto.indexOf('Situação perante a Receita Federal'));
    // Conversão usa os mesmos campos, sem impor dados jurídicos a pessoas físicas.
    pessoa.assistido = null;
    await page.goto(root + '/tornar-assistido');
    await choose('Outros');
    await page.getByLabel('Especifique o enquadramento da PJ', { exact: true }).waitFor();
    await page.getByLabel('Qual o nome do sócio 1?', { exact: true }).waitFor();
    pessoa.pj_constituida = 'nao';
    await page.reload();
    await page.getByRole('button', { name: 'Salvar Assistido', exact: true }).waitFor();
    assert.equal(await page.getByText('Dados Jurídicos', { exact: true }).count(), 0);
    assert.deepEqual(errors, []);
    console.log('OK: conversão, edição, nomes dinâmicos, Outros, MEI, payload, perfil e pessoa física.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
