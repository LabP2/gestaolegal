// Regressões com dados sintéticos. Toda API é interceptada: nenhum banco real é alterado.
const { test, expect } = require("../../web/node_modules/@playwright/test");
const endereco = {
  logradouro: "Rua Teste",
  numero: "10",
  bairro: "Centro",
  cep: "30130-110",
  cidade: "Belo Horizonte",
  estado: "MG",
  complemento: "",
};
const unidades = [{ id: 1, nome: "Belo Horizonte", sigla: "BH", ativa: true }];
const user = {
  id: 1,
  nome: "Admin Teste",
  email: "admin@example.test",
  urole: "admin",
  status: true,
  unidades,
  rg: "123456",
  cpf: "529.982.247-25",
  sexo: "M",
  estado_civil: "solteiro",
  nascimento: "1990-01-15",
  profissao: "Advogado",
  celular: "(31) 99999-1111",
  endereco,
  data_entrada: "2020-01-15",
  bolsista: false,
  cert_atuacao_DAJ: "sim",
  tenant: { sigla: "ENS", djen_ativo: false },
};
const atendido = {
  id: 11,
  nome: "Pessoa Teste",
  cpf: "529.982.247-25",
  data_nascimento: "Mon, 15 Jan 1990 00:00:00 GMT",
  celular: "(31) 99999-1111",
  email: "pessoa@example.test",
  estado_civil: "solteiro",
  como_conheceu: "assist",
  procurou_outro_local: "nao",
  pj_constituida: "nao",
  endereco,
  status: 1,
};
const caso = {
  id: 21,
  descricao: "Descrição original",
  id_usuario_responsavel: 1,
  area_direito: "civel",
  situacao_deferimento: "deferido",
  clientes: [],
  status: true,
  unidade_id: 1,
  usuario_responsavel: user,
  arquivos: [],
  processos: [],
  data_criacao: "2026-01-01",
  criado_por: user,
};
const parceiro = {
  id: 31,
  nome: "Parceiro Teste",
  regiao: "norte",
  areas_atendidas: ["civel"],
  telefone: "(31) 3333-4444",
  email: "parceiro@example.test",
  endereco,
};
const orientacao = {
  id: 41,
  area_direito: "civel",
  sub_area: "familia",
  descricao: "Orientação original",
  atendidos: [],
};
const empty = { items: [], total: 0, total_pages: 0, page: 1 };
async function setup(page, overrides = {}) {
  const db = {
    user: structuredClone(user),
    atendido: structuredClone(atendido),
    caso: structuredClone(caso),
    parceiro: structuredClone(parceiro),
    orientacao: structuredClone(orientacao),
    ...overrides,
  };
  const writes = [];
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.context().addCookies([
    {
      name: "auth_token",
      value: "teste-sintetico",
      url: "http://127.0.0.1:5302",
    },
  ]);
  await page.addInitScript(() => localStorage.setItem("unidade_ativa", "1"));
  await page.route("**/api/**", async (route) => {
    const req = route.request(),
      path = new URL(req.url()).pathname.replace(/\/$/, "");
    const mapping = {
      "/api/user/1": "user",
      "/api/user/2": "user2",
      "/api/atendido/11": "atendido",
      "/api/caso/21": "caso",
      "/api/assistencia_judiciaria/31": "parceiro",
      "/api/orientacao_juridica/41": "orientacao",
    };
    const key = mapping[path];
    let data = empty;
    if (req.method() === "PUT") {
      const body = req.postDataJSON();
      writes.push({ path, body });
      if (overrides.failSave)
        return route.fulfill({
          status: 400,
          json: {
            success: false,
            error: { message: "Falha controlada ao salvar" },
          },
        });
      if (key) db[key] = { ...db[key], ...body };
    }
    if (key) data = db[key];
    else if (path === "/api/user/me") data = db.user;
    else if (path === "/api/user/opcoes") data = { items: [db.user] };
    else if (path === "/api/unidades") data = unidades;
    else if (path.endsWith("/lembretes") || path.endsWith("/arquivos"))
      data = [];
    await route.fulfill({ json: { success: true, data } });
  });
  await page.route("https://viacep.com.br/**", (r) =>
    r.fulfill({ json: { ...endereco, localidade: endereco.cidade, uf: "MG" } }),
  );
  return { db, writes, errors };
}
const scenarios = [
  {
    name: "caso legado",
    url: "/casos/21/editar",
    field: "descricao",
    value: "Caso revisado",
    key: "caso",
  },
  {
    name: "parceiro",
    url: "/plantao/assistencias-judiciarias/31/editar",
    field: "nome",
    value: "Parceiro revisado",
    key: "parceiro",
  },
  {
    name: "atendido",
    url: "/plantao/atendidos-assistidos/11/editar",
    field: "nome",
    value: "Pessoa revisada",
    key: "atendido",
  },
  {
    name: "orientação",
    url: "/plantao/orientacoes-juridicas/41/editar",
    field: "descricao",
    value: "Orientação revisada",
    key: "orientacao",
  },
  {
    name: "usuário",
    url: "/usuarios/1/editar",
    field: "nome",
    value: "Admin Revisado",
    key: "user",
  },
];
for (const s of scenarios)
  test(`editar e recarregar ${s.name}`, async ({ page }) => {
    const { db, writes, errors } = await setup(page);
    await page.goto(s.url);
    const field = page.locator(`[name="${s.field}"]`).first();
    await expect(field).toBeVisible();
    if (s.key === "caso")
      await expect(
        page.getByRole("combobox", { name: "Situação do Deferimento" }),
      ).toBeVisible();
    if (s.key === "atendido")
      await expect(page.locator("[name=data_nascimento]")).toHaveValue(
        "1990-01-15",
      );
    await field.fill(s.value);
    await page.locator("button[type=submit]").first().click();
    await expect.poll(() => writes.length).toBe(1);
    expect(writes[0].body[s.field]).toBe(s.value);
    if (s.key === "caso")
      expect(writes[0].body.situacao_deferimento).toBe("ativo");
    if (s.key === "user") {
      expect(writes[0].body.unidade_ids).toEqual([1]);
      await expect(
        page.getByRole("button", { name: /AR Admin Revisado/ }),
      ).toBeVisible();
    }
    await expect(page).not.toHaveURL(/\/editar$/);
    await page.goto(s.url);
    await expect(page.locator(`[name="${s.field}"]`).first()).toHaveValue(
      db[s.key][s.field],
    );
    expect(errors).toEqual([]);
  });
test("parte sem triagem abre sem inventar CPF e exige preenchimento", async ({
  page,
}) => {
  const { writes } = await setup(page, {
    atendido: {
      ...atendido,
      cpf: null,
      celular: null,
      email: null,
      data_nascimento: null,
      estado_civil: null,
      como_conheceu: null,
      sem_triagem: true,
    },
  });
  await page.goto("/plantao/atendidos-assistidos/11/editar");
  await expect(page.locator("[name=nome]")).toHaveValue("Pessoa Teste");
  await expect(page.locator("[name=cpf]")).toHaveValue("");
  await page.locator("button[type=submit]").first().click();
  await expect(page.locator("[name=cpf]")).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  expect(writes).toHaveLength(0);
});
test("usuário mantém rascunho e mostra erro da API", async ({ page }) => {
  const { writes } = await setup(page, { failSave: true });
  await page.goto("/usuarios/1/editar");
  await page.locator("[name=nome]").fill("Rascunho preservado");
  await page.locator("button[type=submit]").click();
  await expect.poll(() => writes.length).toBe(1);
  await expect(
    page.getByText("Falha controlada ao salvar", { exact: true }),
  ).toBeVisible();
  await expect(page.locator("[name=nome]")).toHaveValue("Rascunho preservado");
  await expect(page).toHaveURL(/\/editar$/);
});
test("API: JSON, multipart e exceções com ou sem captureStackTrace", async ({
  page,
}) => {
  await setup(page);
  await page.goto("/login");
  // Cliente real; apenas ambiente SvelteKit e seleção de unidade são substituídos.
  const { build } = require("../../web/node_modules/esbuild");
  const path = require("node:path");
  const bundle = await build({
    stdin: {
      contents:
        "export { apiFetch } from './src/lib/api-client.ts'; export { ApiException } from './src/lib/types/api-response.ts';",
      resolveDir: path.resolve(__dirname, "../../web"),
    },
    bundle: true,
    write: false,
    format: "iife",
    globalName: "ApiClientTest",
    plugins: [
      {
        name: "ambiente-sintetico",
        setup(build) {
          build.onResolve(
            {
              filter:
                /^\$app\/env(?:\/public)?$|^\.\/stores\/unidade$/,
            },
            (args) => ({ path: args.path, namespace: "teste" }),
          );
          build.onLoad({ filter: /.*/, namespace: "teste" }, (args) => ({
            contents:
              args.path === "$app/env"
                ? "export const dev = false;"
                : args.path === "$app/env/public"
                  ? "export const PUBLIC_API_URL = undefined;"
                  : "export const unidadeAtivaId = () => 1;",
          }));
        },
      },
    ],
  });
  await page.addScriptTag({ content: bundle.outputFiles[0].text });
  const result = await page.evaluate(async () => {
    const { apiFetch, ApiException } = window.ApiClientTest;
    const calls = [];
    const fetcher = async (url, options) => {
      calls.push({
        type: options.headers.get("Content-Type"),
        same: options.body instanceof FormData,
      });
      return new Response("{}");
    };
    await apiFetch(
      "teste",
      { method: "POST", body: '{"nome":"teste"}' },
      fetcher,
    );
    const fd = new FormData();
    fd.append("arquivo", new File(["teste"], "arquivo.txt"));
    await apiFetch("teste", { method: "POST", body: fd }, fetcher);
    await apiFetch(
      "teste",
      {
        method: "POST",
        body: "texto",
        headers: { "Content-Type": "text/plain" },
      },
      fetcher,
    );
    const normal = new ApiException("normal", "CODIGO", null, 400);
    const original = Object.getOwnPropertyDescriptor(
      Error,
      "captureStackTrace",
    );
    let fallback;
    try {
      delete Error.captureStackTrace;
      fallback = new ApiException("fallback").message;
    } finally {
      if (original) Object.defineProperty(Error, "captureStackTrace", original);
    }
    return {
      calls,
      name: normal.name,
      code: normal.code,
      status: normal.statusCode,
      stack: !!normal.stack,
      fallback,
    };
  });
  expect(result).toEqual({
    calls: [
      { type: "application/json", same: false },
      { type: null, same: true },
      { type: "text/plain", same: false },
    ],
    name: "ApiException",
    code: "CODIGO",
    status: 400,
    stack: true,
    fallback: "fallback",
  });
});

test("valor legado fora do enum não é salvo como opção arbitrária", async ({
  page,
}) => {
  const { writes } = await setup(page, {
    parceiro: { ...parceiro, regiao: "regiao-legada" },
  });
  await page.goto("/plantao/assistencias-judiciarias/31/editar");
  await expect(page.locator("[name=nome]")).toHaveValue("Parceiro Teste");
  await page.locator("button[type=submit]").click();
  await expect(
    page.getByText("Selecione a região", { exact: true }),
  ).toBeVisible();
  expect(writes).toHaveLength(0);
});

test("navegação SPA troca o registro do formulário sem reaproveitar dados antigos", async ({
  page,
}) => {
  const { writes } = await setup(page, {
    user2: {
      ...user,
      id: 2,
      nome: "Outra Pessoa",
      email: "outra@example.test",
    },
  });
  await page.goto("/usuarios/1/editar");
  await expect(page.locator("[name=nome]")).toHaveValue("Admin Teste");
  await page.evaluate(() => {
    window.ensaioSPA = true;
    const a = document.createElement("a");
    a.href = "/usuarios/2/editar";
    a.textContent = "Outro registro de teste";
    a.style.cssText =
      "position:fixed;top:0;left:0;z-index:99999;background:white";
    document.body.append(a);
  });
  await page.getByRole("link", { name: "Outro registro de teste" }).click();
  await expect(page.locator("[name=nome]")).toHaveValue("Outra Pessoa");
  expect(await page.evaluate(() => window.ensaioSPA)).toBe(true);
  await page.locator("[name=nome]").fill("Outra Pessoa Editada");
  await page.locator("button[type=submit]").click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0].path).toBe("/api/user/2");
  expect(writes[0].body.email).toBe("outra@example.test");
});

for (const file of ["selector.cjs", "pessoa-juridica.cjs"])
  test(`regressão existente: ${file}`, async () => {
    const { execFile } = require("node:child_process");
    const { promisify } = require("node:util");
    const path = require("node:path");
    await promisify(execFile)(process.execPath, [path.join(__dirname, file)], {
      env: {
        ...process.env,
        PLAYWRIGHT_MODULE: path.resolve(
          __dirname,
          "../../web/node_modules/playwright",
        ),
        GL_BASE_URL: "http://127.0.0.1:5302",
      },
      timeout: 40000,
    });
  });

for (const legacyCpf of ["", null, "123.456.789-00"]) {
  test(`cadastro legado preserva CPF ${JSON.stringify(legacyCpf)} e valida correção`, async ({
    page,
  }) => {
    const { writes, db } = await setup(page, {
      atendido: {
        ...atendido,
        cpf: legacyCpf,
        procurou_outro_local: "",
        pj_constituida: "",
      },
    });
    await page.goto("/plantao/atendidos-assistidos/11/editar");
    await expect(page.getByRole("note")).toBeVisible();
    await page.locator("[name=celular]").fill("31988881234");
    await page.locator("button[type=submit]").first().click();
    await expect.poll(() => writes.length).toBe(1);
    expect(writes[0].body).not.toHaveProperty("cpf");
    expect(writes[0].body).not.toHaveProperty("procurou_outro_local");
    expect(db.atendido.cpf).toBe(legacyCpf);
    await page.goto("/plantao/atendidos-assistidos/11/editar");
    await page.locator("[name=cpf]").fill("11111111111");
    await page.locator("button[type=submit]").first().click();
    await expect(page.locator("[name=cpf]")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(writes).toHaveLength(1);
  });
}
for (const message of [
  "O DJEN não está habilitado para este NPJ.",
  "Você não tem permissão para executar esta ação.",
]) {
  test(`403 preserva mensagem: ${message}`, async ({ page }) => {
    await setup(page);
    await page.route("**/api/djen/**", (route) =>
      route.fulfill({
        status: 403,
        json: { success: false, error: { message, code: "FORBIDDEN" } },
      }),
    );
    await page.goto("/djen");
    await expect(page.getByText(message, { exact: true })).toBeVisible();
  });
}

async function acervoSetup(page) {
  const state = await setup(page, { user: { ...user, tenant: { sigla: 'ENS', djen_ativo: true } } });
  const items = [1, 2].map(id => ({ id, id_djen: 98000 + id, numero_processo: '00000000020268130001', data_disponibilizacao: '2026-11-05', sigla_tribunal: 'TJMG', nome_orgao: 'Vara fictícia', resumo: 'Prazo de quinze dias.', rotulo: 'nao_classificado', origem: 'captura', situacao: 'nao_importada', comunicacao_id: null, id_processo: null, id_caso: null }));
  const actions = [];
  const mudancas = [];
  await page.route('**/api/djen/**', async route => {
    const req = route.request(), url = new URL(req.url());
    let data;
    if (req.method() === 'POST' && url.pathname.endsWith('/desfazer')) {
      // Como no servidor: a reversão restaura o estado anterior pela mudança indicada.
      const body = req.postDataJSON(); actions.push({ path: url.pathname, body });
      const mudanca = mudancas[body.historico_id - 1];
      mudanca.item.rotulo = mudanca.anterior;
      data = { rotulo: mudanca.anterior };
    } else if (req.method() === 'POST') {
      const body = req.postDataJSON(); actions.push({ path: url.pathname, body });
      const historico = {};
      for (const item of items.filter(i => body.ids?.includes(i.id_djen))) {
        if (url.pathname.endsWith('/classificar') && item.rotulo !== body.rotulo) historico[item.id_djen] = mudancas.push({ item, anterior: item.rotulo });
        if (url.pathname.endsWith('/classificar')) item.rotulo = body.rotulo;
        if (url.pathname.endsWith('/importar')) { item.rotulo = 'relevante'; item.situacao = 'vinculada'; item.comunicacao_id = item.id; item.id_processo = 71; }
        if (url.pathname.endsWith('/descartar')) { item.rotulo = 'irrelevante'; item.situacao = 'descartada'; }
      }
      data = { classificadas: body.ids.length, descartadas: body.ids.length, historico };
    } else if (/\/acervo\/\d+$/.test(url.pathname)) {
      const item = items.find(i => i.id === Number(url.pathname.split('/').pop()));
      data = { ...item, texto_plano: '<script>não executar</script> Texto integral fictício', link: 'https://tribunal.exemplo.invalid/documento/98001', link_certidao: 'https://comunicaapi.pje.jus.br/api/v1/comunicacao/hashficticio/certidao', historico: [] };
    } else if (url.pathname.endsWith('/acervo')) {
      const filtro = url.searchParams.get('rotulo');
      const lista = items.filter(i => !filtro || i.rotulo === filtro);
      data = { items: lista, total: lista.length, page: 1, per_page: 20, contextos: [{id:1,nome:'Contexto fictício',nomes:['Parte Teste'],tribunais:[],contagens:{},pode_treinar:false,modelo:null}] };
    } else if (url.pathname.endsWith('/contextos')) data = [{id:1,nome:'Contexto fictício',nomes:['Parte Teste'],tribunais:[],contagens:{},pode_treinar:false,modelo:null}];
    else if (url.pathname.endsWith('/resumo')) data = { total: 2, por_rotulo: {}, por_origem: {}, com_texto: 2 };
    else if (url.pathname.endsWith('/status')) data = { filtros: { tribunais: [], tipos: [] } };
    else data = { items: [], total: 0, page: 1, per_page: 20 };
    await route.fulfill({ json: { success: true, data } });
  });
  return { ...state, actions, items };
}

test('DJEN: treino altera apenas rótulo e mantém decisão ao reabrir', async ({ page }) => {
  const state = await acervoSetup(page);
  state.items[0].texto_plano = '<script>não executar</script> Texto integral fictício';
  await page.goto('/djen/classificacao?contexto_id=1&rotulo=nao_classificado');
  await expect(page.getByRole('heading', { name: 'Acervo para treino' })).toBeVisible();
  await page.getByRole('checkbox', { name: 'Selecionar publicação 98001' }).check();
  await page.getByRole('button', { name: 'Relevante', exact: true }).click();
  await expect(page.getByRole('checkbox', { name: 'Selecionar publicação 98001' })).toHaveCount(0);
  expect(state.actions).toEqual([{ path: '/api/djen/contextos/1/classificar', body: { ids: [98001], rotulo: 'relevante', contexto_ids:[1], id_atendido: null } }]);
  await page.goto('/djen/classificacao?contexto_id=1&rotulo=');
  await expect(page.getByRole('checkbox', { name: 'Selecionar publicação 98001' })).toBeVisible();
  expect(state.items[0].situacao).toBe('nao_importada');
  await page.getByText('Detalhes e histórico',{exact:true}).first().click();
  await expect(page).toHaveURL(/\/djen\/classificacao\?contexto_id=1&rotulo=$/);
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByLabel('Texto integral da publicação').first()).toContainText('<script>não executar</script>');
  await expect(page.getByRole('link', { name: 'Documento no tribunal' })).toHaveAttribute('href', 'https://tribunal.exemplo.invalid/documento/98001');
  await expect(page.getByRole('link', { name: 'Certidão do DJEN (PDF)' })).toHaveAttribute('target', '_blank');
  await expect(page.getByText('Histórico da classificação', {exact:true})).toBeVisible();
  await page.getByText('Detalhes e histórico',{exact:true}).first().click();
  await expect(page).toHaveURL(/\/djen\/classificacao\?contexto_id=1&rotulo=$/);
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(state.errors).toEqual([]);
});

async function importarSemParte(page) {
 await page.getByRole('button',{name:'Importar',exact:true}).click();
 const dialog=page.getByRole('dialog');
 await dialog.getByText('Opções de importação',{exact:true}).click();
 await dialog.getByRole('checkbox',{name:'Importar sem associar parte',exact:true}).check();
 await dialog.getByRole('button',{name:/^Confirmar importação/}).click();
 await expect(dialog).toContainText('Os lotes concluídos estão salvos.');
 await dialog.getByRole('button',{name:'Fechar',exact:true}).click();
}

test('DJEN: importar parte do acervo preserva o restante para depois', async ({ page }) => {
  const state = await acervoSetup(page);
  await page.goto('/djen');
  await page.getByRole('checkbox', { name: 'Selecionar publicação 98001' }).check();
  await importarSemParte(page);
  await expect(page.getByRole('link', { name: 'Processo #71' })).toBeVisible();
  expect(state.items[0].rotulo).toBe('relevante');
  expect(state.items[1].rotulo).toBe('nao_classificado');
  await page.reload();
  await expect(page.getByRole('checkbox', { name: 'Selecionar publicação 98002' })).toBeVisible();
  expect(state.actions).toHaveLength(1);
  expect(state.errors).toEqual([]);
});

test('DJEN: descarte operacional marca irrelevante', async ({ page }) => {
  const state = await acervoSetup(page);
  await page.goto('/djen');
  await page.getByRole('checkbox', { name: 'Selecionar publicação 98002' }).check();
  await page.getByRole('button', { name: 'Descartar', exact: true }).click();
  await expect(page.getByRole('table',{name:'Publicações'}).getByText('Descartado',{exact:true})).toBeVisible();
  expect(state.items[1].rotulo).toBe('irrelevante');
  expect(state.errors).toEqual([]);
});

test('DJEN: monitoramento cadastra, pausa e navega pelas quatro abas', async ({ page }) => {
  await setup(page, { user: { ...user, tenant: { sigla: 'ENS', djen_ativo: true } } });
  let items = [];
  const actions = [];
  await page.route('**/api/djen/monitoramentos**', async route => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    const body = req.method() === 'GET' ? null : req.postDataJSON();
    let data;
    if (path.endsWith('/logs')) data = {items: [],total:0,page:1,per_page:30,retencao_dias:90};
    else if (req.method() === 'POST') {
      actions.push(body);
      items = [{id:1,tipo:body.tipo,valor:body.valor,tribunais:[],ativo:true,automatico:false,unidade_id:1,ultimo_sucesso:null}]; data=items;
    } else if(req.method()==='PATCH') {items[0].ativo=body.ativo;data={};}
    else data=items;
    await route.fulfill({json:{success:true,data}});
  });
  await page.goto('/djen/monitoramento');
  await expect(page.getByRole('heading',{name:'Monitoramento do DJEN'})).toBeVisible();
  await page.getByPlaceholder('123456/MG').fill('123456/MG');
  await page.getByRole('button',{name:'Adicionar ao monitoramento',exact:true}).click();
  await expect(page.getByText('123456/MG',{exact:true})).toBeVisible();
  expect(actions[0].tipo).toBe('oab');
  await page.setViewportSize({width: 768, height: 1024});
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: '/tmp/djen-monitoramento.png', fullPage: true });
  await page.getByRole('button',{name:'Pausar',exact:true}).click();
  await expect(page.getByRole('button',{name:'Retomar',exact:true})).toBeVisible();
  await page.getByRole('link',{name:'Nome da Parte',exact:true}).click();
  await expect(page.getByRole('button',{name:'Adicionar nomes ao monitoramento'})).toBeVisible();
  await page.getByRole('link',{name:'Número do Processo',exact:true}).click();
  await expect(page.getByPlaceholder('0000000-00.0000.0.00.0000')).toBeVisible();
  await page.getByRole('link',{name:'Logs de varredura',exact:true}).click();
  await expect(page.getByText('Nenhuma consulta encontrada.')).toBeVisible();
});

test("processo sem caso: seleciona caso e atualiza detalhes após vincular", async ({ page }) => {
  const { errors } = await setup(page);
  const processo = {
    id: 91, especie: "Ação", numero: "0000001-00.2026.8.13.0000",
    id_caso: null, unidade_id: 1, status: true, id_criado_por: 1,
    partes: [], total_publicacoes: 2
  };
  let enviado;
  await page.route("**/api/processos/91", (route) =>
    route.fulfill({ json: { success: true, data: processo } }));
  await page.route("**/api/caso/?*", (route) =>
    route.fulfill({ json: { success: true, data: { ...empty, items: [caso], total: 1 } } }));
  await page.route("**/api/processos/91/vincular-caso", async (route) => {
    enviado = route.request().postDataJSON();
    processo.id_caso = 21;
    await route.fulfill({ json: { success: true, data: { processo, eventos_criados: 2 } } });
  });
  await page.goto("/processos/91");
  await page.getByRole("button", { name: "Vincular a caso", exact: true }).click();
  await expect(page.getByRole("button", { name: "Confirmar vínculo" })).toBeDisabled();
  await page.getByLabel("Número do caso ou texto da busca").fill("21");
  await page.getByRole("button", { name: "Buscar", exact: true }).click();
  await page.getByRole("radio").check();
  await page.getByRole("button", { name: "Confirmar vínculo" }).click();
  await expect(page.getByRole("link", { name: "Caso #21", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Vincular a caso", exact: true })).toHaveCount(0);
  expect(enviado).toEqual({ caso_id: 21 });
  expect(errors).toEqual([]);
});

for (const tipo of ['oab', 'parte', 'processo']) {
  test(`DJEN: buscar todos os ${tipo} ativos continua após falha`, async ({ page }) => {
    await setup(page, { user: { ...user, tenant: { sigla: 'ENS', djen_ativo: true } } });
    const items = [1,2,3].map(id=>({id,tipo,valor:`Item ${id}`,tribunais:[],ativo:id!==3,unidade_id:id===2?2:1,ultimo_sucesso:null,automatico:false}));
    items.push({...items[0],id:4,tipo:tipo==='oab'?'parte':'oab',valor:'Outro tipo'});
    const calls=[];
    await page.route('**/api/djen/monitoramentos**', async route=>{
      const req=route.request(), path=new URL(req.url()).pathname;
      if(path.endsWith('/buscar')){
        calls.push(req.postDataJSON());
        if(calls.length===1) return route.fulfill({status:503,json:{success:false,error:{message:'Falha simulada'}}});
        return route.fulfill({json:{success:true,data:[{status:'ok',encontradas:2,vinculadas:1}]}});
      }
      await route.fulfill({json:{success:true,data:path.endsWith('/logs')?{items:[],total:0,page:1,per_page:30,retencao_dias:90}:items}});
    });
    await page.goto(`/djen/monitoramento?aba=${tipo}`);
    await page.getByRole('button',{name:'Buscar todos',exact:true}).click();
    await expect.poll(()=>calls.length).toBe(2);
    expect(calls.map(c=>c.valor)).toEqual(['Item 1','Item 2']);
    expect(calls.map(c=>c.unidade_id)).toEqual([1,2]);
    for(const c of calls){
      expect(c.tipo).toBe(tipo);
      expect(c.de).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(c.ate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(c.tribunais).toEqual([]);
      expect(c.historico_completo).toBeUndefined();
    }
    await expect(page.getByText(/1 item\(ns\) com falha/)).toBeVisible();
    await expect(page.getByRole('button',{name:'Buscar todos',exact:true})).toBeEnabled();
  });
}

test('DJEN: CNJ vinculado é link e histórico completo ignora filtros',async({page})=>{
  const state = await acervoSetup(page);
  state.items.forEach(i => i.numero_processo = '00000010020268130001');
  const calls=[];
  const item={id:1,tipo:'processo',valor:'00000010020268130001',processo_id:77,tribunais:[],ativo:true,automatico:true,unidade_id:1,ultimo_sucesso:null};
  await page.route('**/api/djen/monitoramentos**',async route=>{
    const req=route.request(),path=new URL(req.url()).pathname;
    let data;
    if(path.endsWith('/buscar')){calls.push(req.postDataJSON());data=[{status:'ok',encontradas:3,vinculadas:3}];}
    else data=path.endsWith('/logs')?{items:[],total:0,page:1,per_page:30,retencao_dias:90}:[item];
    await route.fulfill({json:{success:true,data}});
  });
  await page.goto('/djen/monitoramento?aba=processo');
  await expect(page.getByRole('link',{name:item.valor,exact:true})).toHaveAttribute('href','/processos/77');
  await page.getByRole('button',{name:'Buscar todas as publicações',exact:true}).last().click();
  await expect.poll(()=>calls.length).toBe(1);
  expect(calls[0]).toEqual({tipo:'processo',valor:item.valor,unidade_id:1,historico_completo:true});
  await expect(page).toHaveURL(`/djen?numero_processo=${item.valor}`);
  await expect(page.getByLabel('Número do processo', {exact:true})).toHaveValue(item.valor);
  await expect(page.getByRole('button',{name:'Revisar',exact:true})).toHaveCount(2);
  expect(state.errors).toEqual([]);
});

test('DJEN: detalhes do processo busca histórico com progresso',async({page})=>{
  await setup(page,{user:{...user,tenant:{sigla:'ENS',djen_ativo:true}}});
  const processo={id:91,especie:'Ação',numero:'00000010020268130001',numero_cnj:'00000010020268130001',id_caso:null,unidade_id:1,status:true,id_criado_por:1,partes:[],total_publicacoes:0};
  await page.route('**/api/processos/91',r=>r.fulfill({json:{success:true,data:processo}}));
  let concluir;
  const aguardar=new Promise(resolve=>{concluir=resolve;});
  let chamadas=0;
  await page.route('**/api/processos/91/djen/buscar',async r=>{
    chamadas++;await aguardar;
    await r.fulfill({json:{success:true,data:{novas:3,atualizadas:0,vinculadas:3,djen_consultado_em:'2026-11-17T12:00:00'}}});
  });
  await page.goto('/processos/91');
  await page.getByRole('button',{name:'Buscar todas as publicações',exact:true}).click();
  await expect(page.getByRole('progressbar')).toBeVisible();
  concluir();
  await expect(page.getByText('3 publicação(ões) nova(s) no DJEN.',{exact:true})).toBeVisible();
  await expect(page.getByRole('progressbar')).toHaveCount(0);
  expect(chamadas).toBe(1);
});

test('DJEN: detalhes do acervo usam o ID operacional correto e preservam filtros',async({page})=>{
  const state=await acervoSetup(page);
  Object.assign(state.items[0],{rotulo:'relevante',situacao:'vinculada',comunicacao_id:5,id_processo:77,id_caso:31});
  await page.route('**/api/djen/publicacoes/5',r=>r.fulfill({json:{success:true,data:{
    ...state.items[0],id:5,ativo:true,tipo_comunicacao:'Intimação',
    destinatarios:[],advogados:[],texto_html_seguro:'<p>Texto operacional seguro.</p>',pode_vincular:false
  }}}));
  await page.goto('/djen?rotulo=relevante');
  await page.getByRole('button',{name:'Revisar',exact:true}).click();
  await page.getByRole('link',{name:'Ler publicação e histórico',exact:true}).click();
  await expect(page).toHaveURL(/\/djen\/acervo\/1\?/);
  await expect(page.getByRole('link',{name:'Abrir operação',exact:true})).toHaveAttribute('href','/djen/publicacoes/5');
  await expect(page.getByRole('link',{name:'Abrir processo',exact:true})).toHaveAttribute('href','/processos/77');
  await expect(page.getByRole('link',{name:'Abrir caso',exact:true})).toHaveAttribute('href','/casos/31');
  await expect(page.getByText('Destinatários',{exact:true})).toBeVisible();
  await expect(page.getByText('Advogados',{exact:true})).toBeVisible();
  await page.getByRole('link',{name:'Voltar',exact:true}).click();
  await expect(page).toHaveURL(/\/djen\?rotulo=relevante$/);
  await page.getByRole('button',{name:'Revisar',exact:true}).click();
  await page.getByRole('link',{name:'Ler publicação e histórico',exact:true}).click();
  await page.getByRole('link',{name:'Abrir operação',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Intimação',exact:true})).toBeVisible();
  await expect(page.getByRole('region',{name:'Texto da publicação'})).toHaveText('Texto operacional seguro.');
  expect(state.errors).toEqual([]);
});

test('DJEN: monitoramento por nome explica tribunal obrigatório e permite corrigir', async ({ page }) => {
  const { errors } = await setup(page, { user: { ...user, tenant: { sigla: 'ENS', djen_ativo: true } } });
  const actions = [];
  await page.route('**/api/djen/monitoramentos**', async route => {
    const req = route.request();
    if (req.method() === 'POST') actions.push(req.postDataJSON());
    const data = new URL(req.url()).pathname.endsWith('/logs')
      ? { items: [], total: 0, page: 1, per_page: 30, retencao_dias: 90 } : [];
    await route.fulfill({ json: { success: true, data } });
  });
  await page.goto('/djen/monitoramento?aba=parte');
  await page.getByLabel('Nome da parte', { exact: true }).fill('Pessoa de Teste');
  await page.getByRole('button', { name: 'Adicionar nomes ao monitoramento' }).click();
  const tribunais = page.getByRole('combobox', { name: 'Tribunais', exact: true });
  await expect(tribunais).toHaveAttribute('aria-invalid', 'true');
  await expect(page.getByRole('alert').filter({ hasText: 'Para monitorar por nome' })).toBeVisible();
  expect(actions).toEqual([]);
  await tribunais.click();
  await page.getByRole('option', { name: 'TJMG', exact: true }).click();
  await page.keyboard.press('Escape');
  await expect(tribunais).not.toHaveAttribute('aria-invalid', 'true');
  await page.getByRole('button', { name: 'Adicionar nomes ao monitoramento' }).click();
  await expect.poll(() => actions.length).toBe(1);
  expect(actions[0]).toEqual({ tipo: 'parte', valor: 'Pessoa de Teste', tribunais: ['TJMG'] });
  expect(errors).toEqual([]);
});

test('DJEN: sugestões por contexto divergem e operação recebe escolha explícita', async ({page}) => {
 const state=await acervoSetup(page);
 const contextos=[{id:1,nome:'UFMG — TRF6',nomes:['UFMG'],tribunais:['TRF6'],contagens:{},pode_treinar:false,modelo:null},{id:2,nome:'UFMG — todos',nomes:['UFMG'],tribunais:[],contagens:{},pode_treinar:false,modelo:null}];
 state.items[0].contextos=contextos.map((c,i)=>({contexto_id:c.id,nome:c.nome,rotulo:'nao_classificado',sugestao:i?'irrelevante':'relevante',modelo_id:c.id,origem:'captura'}));
 await page.route('**/api/djen/acervo?**',async route=>{
  const url=new URL(route.request().url());const cid=Number(url.searchParams.get('contexto_id'));
  await route.fulfill({json:{success:true,data:{items:state.items.map(i=>({...i,contextos:(i.contextos??[]).filter(c=>!cid||c.contexto_id===cid)})),total:2,page:1,per_page:20,contextos}}});
 });
 await page.goto('/djen');
 await expect(page.getByText('Sugestões divergentes',{exact:true})).toBeVisible();
 await page.setViewportSize({width:768,height:1024});
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:'/tmp/djen-contextos-ui.png',fullPage:true});
 await page.getByRole('checkbox',{name:'Selecionar publicação 98001'}).check();
 await page.getByText('Avaliar contextos ao importar ou descartar',{exact:true}).click();
 await page.getByRole('checkbox',{name:'UFMG — TRF6',exact:true}).check();
 await importarSemParte(page);
 await expect.poll(()=>state.actions.length).toBe(1);
 expect(state.actions[0].body.contexto_ids).toEqual([1]);
 await expect(page.getByText('Nenhuma selecionada',{exact:true})).toBeVisible();
 await expect(page.getByText(/publicações importadas\./)).toBeVisible();
 await expect(page.getByRole('combobox',{name:'Contexto de classificação',exact:true})).not.toBeVisible();
 await page.getByText('Filtros avançados',{exact:true}).click();
 await page.getByRole('combobox',{name:'Contexto de classificação',exact:true}).click();
 await page.getByRole('option',{name:'UFMG — todos',exact:true}).click();
 await expect(page).toHaveURL(/contexto_id=2/);
 await expect(page.getByText('Sugestões divergentes',{exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Revisar',exact:true}).first().click();
 await expect(page.getByText(/Sugestão: Irrelevante · modelo #2/)).toBeVisible();
 await page.getByRole('combobox',{name:'Sugestão do modelo',exact:true}).click();
 await page.getByRole('option',{name:'Irrelevante',exact:true}).click();
 await expect(page).toHaveURL(/sugestao=irrelevante/);
 expect(new URL(page.url()).searchParams.get('contexto_id')).toBe('2');
 await expect(page.getByText('Contexto: UFMG — todos',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Limpar contexto de classificação'}).click();
 await expect.poll(() => new URL(page.url()).searchParams.get('contexto_id')).toBeNull();
 expect(new URL(page.url()).searchParams.get('sugestao')).toBe('irrelevante');
 expect(state.errors).toEqual([]);
});

test('DJEN: acervo de treino abre todas e cria contexto no card de filtros sem etapa de prévia', async ({ page }) => {
 const state = await acervoSetup(page); let corpo; let previas = 0;
 await page.route('**/api/djen/contextos/previa', route => { previas++; return route.fulfill({json:{success:true,data:{total:2,entram:2,saem:0,permanecem:0}}}); });
 await page.route('**/api/djen/contextos', async route => {
  if (route.request().method() === 'GET') return route.fallback();
  corpo=route.request().postDataJSON(); await route.fulfill({json:{success:true,data:{id:1,...corpo}}});
 });
 await page.goto('/djen/classificacao?tribunal=TJMG&fonte=oab');
 await expect(page.getByRole('checkbox',{name:'Selecionar publicação 98001'})).toBeVisible();
 await expect(page.getByRole('button',{name:'Relevante',exact:true})).toBeDisabled();
 await expect(page.getByLabel('OAB',{exact:true})).toBeVisible();
 await expect(page.getByRole('combobox',{name:'Situação operacional',exact:true})).toBeVisible();
 await expect(page.getByRole('combobox',{name:'Origem da consulta',exact:true})).toBeVisible();
 const filtros = page.getByRole('region', {name:'Filtros de publicações'});
 await filtros.getByRole('button',{name:'Criar contexto',exact:true}).click();
 const form = filtros.getByRole('form', {name:'Criar contexto',exact:true});
 await form.getByLabel('Nome do contexto',{exact:true}).fill('UFMG — TJMG');
 await form.getByLabel('Descrição',{exact:true}).fill('Publicações de interesse da universidade');
 await expect(form.getByLabel('OAB',{exact:true})).toHaveCount(0);
 await expect(form.getByRole('button',{name:'Conferir contexto'})).toHaveCount(0);
 // O salvamento também deve ler alterações que ainda aguardam o debounce.
 await filtros.getByLabel('Nome da parte',{exact:true}).fill('UFMG');
 await form.getByRole('button',{name:'Salvar contexto'}).click();
 await expect(page).toHaveURL(/contexto_id=1/);
 expect(corpo.nome).toBe('UFMG — TJMG');
 expect(corpo.descricao).toBe('Publicações de interesse da universidade');
 expect(previas).toBe(0);
 expect(corpo.criterios.nome_parte).toBe('UFMG');
 expect(corpo.criterios.tribunal).toEqual(['TJMG']);
 expect(corpo.criterios.fonte).toBe('oab');
 await expect(page.getByRole('button',{name:'Treinar modelo experimental'})).toBeDisabled();
 await expect(page.getByRole('combobox',{name:'Avaliação neste contexto',exact:true})).toBeVisible();
 await page.getByLabel('Número do processo',{exact:true}).fill('00000000020268130001');
 await expect(page).toHaveURL(/numero_processo=00000000020268130001/);
 expect(new URL(page.url()).searchParams.get('contexto_id')).toBe('1');
 // Decisão de 20/11/2026: os critérios ficam no contexto e não são herdados pela URL.
 expect(new URL(page.url()).searchParams.has('tribunal')).toBe(false);
 await page.setViewportSize({width:768,height:1024});
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:'/tmp/djen-treino-criterios.png',fullPage:true});
 expect(state.errors).toEqual([]);
});

test('DJEN: card mostra partes, confirma sugestão e lote permite sem parte', async ({ page }) => {
  const state = await acervoSetup(page);
  state.items[0].partes = ['Fulana Fictícia', 'Empresa Fictícia'];
  state.items[0].atendidos_sugeridos = [{id:42,nome:'Fulana Fictícia'}];
  state.items[1].atendidos_sugeridos = [{id:43,nome:'Homônimo'}, {id:44,nome:'Homônimo'}];
  await page.goto('/djen');
  await expect(page.getByText('Fulana Fictícia · Empresa Fictícia')).toBeVisible();
  await page.getByRole('button',{name:'Revisar',exact:true}).first().click();
  await page.getByRole('button',{name:'Revisar',exact:true}).first().click();
  await expect(page.getByRole('combobox',{name:'Parte da publicação 98001'})).toContainText('Fulana Fictícia');
  await expect(page.getByRole('combobox',{name:'Parte da publicação 98002'})).toContainText('Sem parte selecionada');
  await expect(page.getByRole('button',{name:'Selecionar Atendidos',exact:true})).toHaveCount(0);
  await page.setViewportSize({width:768,height:1024});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({path:'/tmp/djen-partes-cards.png',fullPage:true});
  await page.getByRole('button',{name:'Confirmar parte e importar'}).click();
  await expect(page.getByRole('link',{name:'Processo #71'})).toBeVisible();
  expect(state.actions[0].body).toMatchObject({ids:[98001],id_atendido:42,sem_parte:false});
  await page.getByRole('checkbox',{name:'Selecionar publicação 98002'}).check();
  await importarSemParte(page);
  await expect(page.getByRole('link',{name:'Processo #71'})).toHaveCount(2);
  expect(state.actions[1].body).toMatchObject({ids:[98002],id_atendido:null,sem_parte:true});
  expect(state.errors).toEqual([]);
});

test('DJEN: treino entra na fila, atualiza status e mostra erro recuperável', async ({page}) => {
  await acervoSetup(page);
  const ctx={id:1,nome:'Contexto assíncrono',nomes:['Parte Teste'],tribunais:[],contagens:{relevante:120,irrelevante:120},pode_treinar:true,modelo:null,treino_status:'ocioso',treino_erro:null};
  let pedidos=0;
  await page.route('**/api/djen/contextos',route=>route.fulfill({json:{success:true,data:[ctx]}}));
  await page.route('**/api/djen/acervo?**',route=>route.fulfill({json:{success:true,data:{items:[],total:0,page:1,per_page:20,contextos:[ctx]}}}));
  await page.route('**/api/djen/contextos/1/treinar',route=>{
    pedidos++;ctx.treino_status='na_fila';
    return route.fulfill({status:202,json:{success:true,data:ctx}});
  });
  await page.goto('/djen/classificacao?contexto_id=1&rotulo=');
  await page.getByRole('button',{name:'Treinar modelo experimental',exact:true}).click();
  await expect(page.getByText('Treino na fila. Aguardando o processamento em segundo plano.',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Treino em andamento…',exact:true})).toBeDisabled();
  ctx.treino_status='executando';
  await expect(page.getByText('Treinando modelo em segundo plano. Você pode sair desta tela.',{exact:true})).toBeVisible({timeout:10000});
  ctx.treino_status='erro';ctx.treino_erro='Tempo excedido. Solicite novamente.';
  await expect(page.getByRole('alert')).toContainText('Tempo excedido',{timeout:10000});
  await expect(page.getByRole('button',{name:'Treinar modelo experimental',exact:true})).toBeEnabled();
  expect(pedidos).toBe(1);
});

test('DJEN lote sugerido: revisa seleção e exclui ambiguidades', async ({page}) => {
  const state = await acervoSetup(page);
  state.items[0].atendidos_sugeridos = [{id:42,nome:'UFMG'}];
  state.items[1].numero_processo = '00000000120268130001';
  state.items[1].atendidos_sugeridos = [{id:43,nome:'Homônimo'}, {id:44,nome:'Homônimo'}];
  await page.goto('/djen?nome_parte=UFMG');
  await page.getByRole('checkbox',{name:'Selecionar esta página'}).check();
  await page.getByRole('button',{name:'Importar',exact:true}).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('1 publicações aptas');
  await expect(dialog).toContainText('1 fora do lote');
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await expect(dialog).toHaveCSS('opacity','1');
  await page.screenshot({path:'/tmp/djen-importar-lote.png',animations:'disabled'});
  expect(state.actions).toHaveLength(0);
  await dialog.getByRole('button',{name:/^Confirmar importação/}).click();
  await expect(dialog).toContainText('1 de 1 importadas');
  expect(state.actions).toHaveLength(1);
  expect(state.actions[0].body).toMatchObject({ids:[98001],id_atendido:42,sem_parte:false});
  expect(state.errors).toEqual([]);
});

test('DJEN lote sugerido: todo filtro pagina, divide lotes e retoma falha', async ({page}) => {
  const state = await acervoSetup(page);
  const items = Array.from({length:205},(_,i)=>({...state.items[0],id:i+1,id_djen:99000+i,
    numero_processo:String(i).padStart(20,'0'),atendidos_sugeridos:[{id:42,nome:'UFMG'}]}));
  const leituras=[], chamadas=[];
  let falhar=true;
  await page.route('**/api/djen/acervo?**',route=>{
    const p=new URL(route.request().url()).searchParams;
    leituras.push(Object.fromEntries(p));
    const n=Number(p.get('page')||1), tamanho=Number(p.get('per_page')||20);
    return route.fulfill({json:{success:true,data:{items:items.slice((n-1)*tamanho,n*tamanho),total:items.length,page:n,per_page:tamanho,contextos:[]}}});
  });
  await page.route('**/api/djen/busca-parte/importar',route=>{
    const body=route.request().postDataJSON(); chamadas.push(body);
    if(chamadas.length===2 && falhar) {
      falhar=false;
      return route.fulfill({status:500,json:{success:false,error:{message:'Falha simulada'}}});
    }
    return route.fulfill({json:{success:true,data:{}}});
  });
  await page.goto('/djen?nome_parte=UFMG&tribunal=TRT3&situacao=nao_importada');
  await page.getByRole('button',{name:'Importar',exact:true}).click();
  const dialog=page.getByRole('dialog');
  await expect(dialog).toContainText('205 publicações aptas');
  expect(chamadas).toHaveLength(0);
  expect(leituras.filter(p=>p.per_page==='100').map(p=>p.page)).toEqual(['1','2','3']);
  for(const p of leituras) expect(p).toMatchObject({nome_parte:'UFMG',tribunal:'TRT3',situacao:'nao_importada'});
  await dialog.getByRole('button',{name:/^Confirmar importação/}).click();
  await expect(dialog.getByRole('alert')).toContainText('Falha simulada');
  await expect(dialog).toContainText('100 de 205 importadas');
  await dialog.getByRole('button',{name:'Continuar importação'}).click();
  await expect(dialog).toContainText('205 de 205 importadas');
  expect(chamadas.map(c=>c.ids.length)).toEqual([100,100,100,5]);
  expect(chamadas[1].ids).toEqual(chamadas[2].ids);
  expect(chamadas[0].ids.some(id=>chamadas[2].ids.includes(id))).toBe(false);
  for(const body of chamadas) expect(body).toMatchObject({id_atendido:42,sem_parte:false,contexto_ids:[]});
  expect(state.errors).toEqual([]);
});

test('DJEN lote sugerido: não associa partes divergentes ao mesmo processo', async ({page}) => {
  const state=await acervoSetup(page);
  state.items[0].atendidos_sugeridos=[{id:42,nome:'Parte A'}];
  state.items[1].atendidos_sugeridos=[{id:43,nome:'Parte B'}];
  await page.goto('/djen');
  await page.getByRole('button',{name:'Importar',exact:true}).click();
  const dialog=page.getByRole('dialog');
  await expect(dialog).toContainText('0 publicações aptas');
  await expect(dialog).toContainText('2 fora do lote');
  await expect(dialog.getByRole('button',{name:/^Confirmar importação/})).toBeDisabled();
  expect(state.actions).toHaveLength(0);
});

for(const tela of ['casos','djen']) test(`Paginação simétrica: ${tela}, filtros e tamanho preservados`,async({page})=>{
 const state=tela==='djen'?await acervoSetup(page):await setup(page);
 const endpoint=tela==='djen'?'djen/acervo':'caso';
 await page.route(`**/api/${endpoint}?**`,route=>{
  const p=new URL(route.request().url()).searchParams;
  const n=Number(p.get('page')||1),t=Number(p.get('per_page')||20);
  const item=tela==='djen'?{...state.items[0],partes:['UFMG'],atendidos_sugeridos:[{id:42,nome:'UFMG'}]}:caso;
  return route.fulfill({json:{success:true,data:{items:[item],total:205,page:n,per_page:t,contextos:[]}}});
 });
 await page.goto(`/${tela}`);
 const paginacao=page.getByRole('navigation',{name:'Paginação',exact:true});
 await expect(paginacao).toContainText('Página 1 de 11');
 await expect(paginacao.getByRole('button',{name:'Primeira página',exact:true})).toBeDisabled();
 const campo=page.getByLabel(tela==='djen'?'Nome da parte':'Descrição ou parte envolvida',{exact:true});
 await campo.fill('UFMG');
 const chave=tela==='djen'?'nome_parte':'search';
 await expect.poll(()=>new URL(page.url()).searchParams.get(chave)).toBe('UFMG');
 await paginacao.getByRole('button',{name:'Próxima página',exact:true}).click();
 await expect(paginacao).toContainText('Página 2 de 11');
 expect(new URL(page.url()).searchParams.get(chave)).toBe('UFMG');
 await page.getByLabel('Resultados por página').selectOption('50');
 await expect(paginacao).toContainText('Página 1 de 5');
 expect(new URL(page.url()).searchParams.get(chave)).toBe('UFMG');
 await paginacao.getByRole('button',{name:'Última página',exact:true}).click();
 await expect(paginacao).toContainText('Mostrando 201 a 205 de 205 resultados');
 await expect(paginacao.getByRole('button',{name:'Próxima página',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'Limpar filtros',exact:true}).click();
 await expect(campo).toHaveValue('');
 await expect(page.getByLabel('Resultados por página')).toHaveValue('50');
 await expect(paginacao).toContainText('Página 1 de 5');
 expect(new URL(page.url()).searchParams.get(chave)||'').toBe('');
 if(tela==='djen'){
  await expect(page.getByRole('columnheader',{name:'Atendido sugerido'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Confirmar parte e importar'})).toHaveCount(0);
  await page.screenshot({path:'/tmp/djen-simetria-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await expect(page.getByRole('columnheader',{name:'Atendido sugerido'})).toBeHidden();
  await page.getByRole('button',{name:'Revisar',exact:true}).click();
  await expect(page.getByRole('button',{name:'Confirmar parte e importar'})).toBeVisible();
  await page.screenshot({path:'/tmp/djen-simetria-mobile.png',fullPage:true});
 }
 expect(state.errors).toEqual([]);
});

test('DJEN: ícones na linha mostram parte e exigem confirmação para importar',async({page})=>{
 const state=await acervoSetup(page);
 state.items[0].atendidos_sugeridos=[{id:42,nome:'Universidade Federal de Minas Gerais'}];
 await page.goto('/djen');
 const parte=page.getByRole('button',{name:'Parte sugerida: Universidade Federal de Minas Gerais',exact:true});
 await expect(parte).toHaveAttribute('title','Parte sugerida: Universidade Federal de Minas Gerais');
 await parte.click();
 const dialog=page.getByRole('dialog');
 await expect(dialog).toContainText('Universidade Federal de Minas Gerais');
 expect(state.actions).toHaveLength(0);
 await page.keyboard.press('Escape');
 await page.getByRole('button',{name:'Importar publicação',exact:true}).first().click();
 expect(state.actions).toHaveLength(0);
 await dialog.getByRole('button',{name:'Confirmar parte e importar',exact:true}).click();
 await expect(page.getByRole('link',{name:'Processo #71'})).toBeVisible();
 expect(state.actions[0].body).toMatchObject({ids:[98001],id_atendido:42,sem_parte:false});
 await expect(page.getByRole('button',{name:'Importar publicação',exact:true})).toHaveCount(1);
 await page.getByRole('link',{name:'Ler publicação',exact:true}).first().click();
 await expect(page).toHaveURL(/\/djen\/acervo\/1\?/);
 expect(state.errors).toEqual([]);
});

test('DJEN: filtro múltiplo de tribunais persiste na paginação e no lote',async({page})=>{
 const state=await acervoSetup(page);
 state.items[0].atendidos_sugeridos=[{id:42,nome:'UFMG'}];
 const consultas=[];
 await page.route('**/api/djen/acervo?**',route=>{
  const p=new URL(route.request().url()).searchParams;
  consultas.push(Object.fromEntries(p));
  const n=Number(p.get('page')||1),t=Number(p.get('per_page')||20);
  return route.fulfill({json:{success:true,data:{items:state.items,total:40,page:n,per_page:t,contextos:[]}}});
 });
 await page.goto('/djen');
 const trigger=page.getByRole('combobox',{name:'Tribunais',exact:true});
 await trigger.click();
 await page.getByRole('option',{name:'TJMG',exact:true}).click();
 await page.getByRole('option',{name:'TRT3',exact:true}).click();
 await page.keyboard.press('Escape');
 await expect(trigger).toContainText('TJMG, TRT3');
 await expect.poll(()=>new URL(page.url()).searchParams.get('tribunal')).toBe('TJMG,TRT3');
 await page.getByRole('button',{name:'Próxima página',exact:true}).click();
 await expect.poll(()=>new URL(page.url()).searchParams.get('page')).toBe('2');
 await expect(trigger).toContainText('TJMG, TRT3');
 await page.reload();
 await expect(trigger).toContainText('TJMG, TRT3');
 await page.getByRole('button',{name:'Importar',exact:true}).click();
 await expect(page.getByRole('dialog')).toContainText('1 publicações aptas');
 expect(consultas.find(p=>p.per_page==='100')).toMatchObject({tribunal:'TJMG,TRT3'});
 await page.getByRole('button',{name:'Fechar',exact:true}).click();
 await page.getByRole('button',{name:'Limpar filtros',exact:true}).click();
 await expect(trigger).toHaveText('Todos os tribunais');
 expect(state.actions).toHaveLength(0);
 expect(state.errors).toEqual([]);
});

test('DJEN: importação simples escolhe alcance antes de confirmar',async({page})=>{
 const state=await acervoSetup(page);
 for(const item of state.items)item.atendidos_sugeridos=[{id:42,nome:'UFMG'}];
 await page.goto('/djen');
 await expect(page.getByRole('button',{name:'Importar',exact:true})).toHaveCount(1);
 await expect(page.getByRole('button',{name:'Mais ações',exact:true})).toHaveCount(0);
 await page.getByRole('checkbox',{name:'Selecionar publicação 98001'}).check();
 await page.getByRole('button',{name:'Importar',exact:true}).click();
 const dialog=page.getByRole('dialog');
 await expect(dialog.getByRole('radio',{name:'Selecionadas (1)',exact:true})).toBeChecked();
 await expect(dialog).toContainText('1 publicações aptas');
 await dialog.getByRole('radio',{name:'Todas do filtro (2)',exact:true}).check();
 await expect(dialog).toContainText('2 publicações aptas');
 expect(state.actions).toHaveLength(0);
 await dialog.getByRole('radio',{name:'Selecionadas (1)',exact:true}).check();
 await expect(dialog.getByRole('button',{name:'Confirmar importação (1)',exact:true})).toBeEnabled();
 await dialog.getByRole('button',{name:'Confirmar importação (1)',exact:true}).click();
 await expect(dialog).toContainText('1 de 1 importadas');
 expect(state.actions).toHaveLength(1);
 expect(state.actions[0].body).toMatchObject({ids:[98001],id_atendido:42,sem_parte:false});
 expect(state.errors).toEqual([]);
});

test('DJEN: polo da parte acompanha nome, paginação e importação',async({page})=>{
 const state=await acervoSetup(page);
 state.items[0].atendidos_sugeridos=[{id:42,nome:'UFMG'}];
 const consultas=[];
 await page.route('**/api/djen/acervo?**',route=>{
  const p=new URL(route.request().url()).searchParams;
  consultas.push(Object.fromEntries(p));
  return route.fulfill({json:{success:true,data:{items:state.items,total:40,page:Number(p.get('page')||1),per_page:Number(p.get('per_page')||20),contextos:[]}}});
 });
 await page.goto('/djen?nome_parte=UFMG');
 const polo=page.getByRole('combobox',{name:'Polo da parte',exact:true});
 await polo.click();
 await page.getByRole('option',{name:'Passivo',exact:true}).click();
 await expect.poll(()=>new URL(page.url()).searchParams.get('polo')).toBe('P');
 expect(new URL(page.url()).searchParams.get('nome_parte')).toBe('UFMG');
 await page.getByRole('button',{name:'Próxima página',exact:true}).click();
 await expect.poll(()=>new URL(page.url()).searchParams.get('page')).toBe('2');
 await expect(polo).toContainText('Passivo');
 await page.reload();
 await expect(polo).toContainText('Passivo');
 await page.getByRole('button',{name:'Importar',exact:true}).click();
 await expect(page.getByRole('dialog')).toContainText('1 publicações aptas');
 expect(consultas.find(p=>p.per_page==='100')).toMatchObject({polo:'P',nome_parte:'UFMG'});
 await page.getByRole('button',{name:'Fechar',exact:true}).click();
 await page.getByRole('button',{name:'Limpar filtros',exact:true}).click();
 await expect(polo).toHaveText('Todos');
 expect(state.actions).toHaveLength(0);
 expect(state.errors).toEqual([]);
});

test('DJEN: exporta somente selecionadas com texto completo e CSV seguro', async ({ page }) => {
  const state = await acervoSetup(page);
  state.items[0].partes = ['João; "Silva"', '=HYPERLINK("https://example.invalid")'];
  state.items[0].nome_orgao = '=1+1';
  await page.route('**/api/djen/acervo/1', route => route.fulfill({ json: { success: true, data: {
    ...state.items[0], texto_plano: 'Intimação; "íntegra"\nSegunda linha.', link: null, link_certidao: null
  } } }));
  await page.goto('/djen');
  const exportar = page.getByRole('button', { name: 'Exportar selecionadas', exact: true });
  await expect(exportar).toBeDisabled();
  await page.getByRole('checkbox', { name: 'Selecionar publicação 98001' }).check();
  const downloadPromise = page.waitForEvent('download');
  await exportar.click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^publicacoes-djen-\d{4}-\d{2}-\d{2}\.csv$/);
  const stream = await download.createReadStream();
  const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  const csv = Buffer.concat(chunks).toString('utf8');
  expect(csv.startsWith('\uFEFF')).toBe(true);
  expect(csv).toContain('"98001";"05/11/2026"');
  expect(csv).not.toContain('98002');
  expect(csv).toContain('"0000000-00.2026.8.13.0001"');
  expect(csv).toContain('"\'=1+1"');
  expect(csv).toContain('João; ""Silva""');
  expect(csv).toContain('"Intimação; ""íntegra""\nSegunda linha."');
  expect(state.actions).toEqual([]);
  await expect(page.getByRole('checkbox', { name: 'Selecionar publicação 98001' })).toBeChecked();
});

test('DJEN: falha na exportação mantém seleção e permite tentar novamente', async ({ page }) => {
  await acervoSetup(page);
  await page.route('**/api/djen/acervo/2', route => route.fulfill({ status: 500, json: {
    success: false, error: { message: 'Falha ao obter publicação.' }
  } }));
  await page.goto('/djen');
  await page.getByRole('checkbox', { name: 'Selecionar esta página' }).check();
  const downloads = [];
  page.on('download', download => downloads.push(download));
  await page.getByRole('button', { name: 'Exportar selecionadas', exact: true }).click();
  await expect(page.getByText('Falha ao obter publicação.', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Exportar selecionadas', exact: true })).toBeEnabled();
  await expect(page.getByRole('checkbox', { name: 'Selecionar publicação 98002' })).toBeChecked();
  expect(downloads).toHaveLength(0);
});

async function acervoPaginado(page, quantidade = 3) {
  const state = await acervoSetup(page);
  const modelo = state.items[0];
  state.items.splice(0, state.items.length, ...Array.from({ length: quantidade }, (_, i) => ({
    ...modelo, id: i + 1, id_djen: 98001 + i
  })));
  const consultas = [];
  await page.route('**/api/djen/acervo?**', route => {
    const params = new URL(route.request().url()).searchParams;
    consultas.push(Object.fromEntries(params));
    const pagina = Number(params.get('page') || 1);
    const tamanho = Math.min(Number(params.get('per_page') || 2), quantidade === 3 ? 2 : 100);
    return route.fulfill({ json: { success: true, data: {
      items: state.items.slice((pagina - 1) * tamanho, pagina * tamanho),
      total: quantidade, page: pagina, per_page: tamanho, contextos: []
    } } });
  });
  return { ...state, consultas };
}

test('DJEN: selecionar todas exporta outras páginas respeitando filtros e exclusões', async ({ page }) => {
  const state = await acervoPaginado(page);
  await page.goto('/djen?tribunal=TJMG&nome_parte=João');
  await page.getByRole('checkbox', { name: 'Selecionar todas (3)', exact: true }).check();
  await expect(page.getByText('3 selecionadas', { exact: true })).toBeVisible();
  expect(state.consultas.filter(c => c.per_page === '100')).toEqual([]);
  await page.getByRole('checkbox', { name: 'Selecionar esta página', exact: true }).uncheck();
  await expect(page.getByText('1 selecionadas', { exact: true })).toBeVisible();
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Exportar selecionadas', exact: true }).click();
  const download = await downloadPromise;
  const stream = await download.createReadStream();
  const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  const csv = Buffer.concat(chunks).toString('utf8');
  expect(state.consultas.filter(c => c.per_page === '100')).toEqual([
    { tribunal: 'TJMG', nome_parte: 'João', per_page: '100', page: '1' },
    { tribunal: 'TJMG', nome_parte: 'João', per_page: '100', page: '2' }
  ]);
  expect(csv).toContain('"98003";');
  expect(csv).not.toContain('"98001";');
  expect(csv).not.toContain('"98002";');
  await page.getByRole('checkbox', { name: 'Selecionar todas (3)', exact: true }).check();
  await expect(page.getByText('3 selecionadas', { exact: true })).toBeVisible();
  await page.getByRole('checkbox', { name: 'Selecionar todas (3)', exact: true }).uncheck();
  await expect(page.getByText('Nenhuma selecionada', { exact: true })).toBeVisible();
});

test('DJEN: selecionar todas inclui outras páginas na importação e divide descarte em lotes', async ({ page }) => {
  const state = await acervoPaginado(page, 101);
  await page.goto('/djen');
  await page.getByRole('checkbox', { name: 'Selecionar todas (101)', exact: true }).check();
  await expect(page.getByText('101 selecionadas', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Importar', exact: true }).click();
  await expect(page.getByRole('radio', { name: 'Selecionadas (101)', exact: true })).toBeChecked();
  await page.getByRole('button', { name: 'Fechar', exact: true }).click();
  await page.getByRole('button', { name: 'Descartar', exact: true }).click();
  await expect.poll(() => state.actions.length).toBe(2);
  expect(state.actions.map(a => a.body.ids.length)).toEqual([100, 1]);
  expect(new Set(state.actions.flatMap(a => a.body.ids)).size).toBe(101);
  await expect(page.getByText('Nenhuma selecionada', { exact: true })).toBeVisible();
});

test('DJEN: falha ao carregar seleção completa não exporta parcialmente e preserva exclusões', async ({ page }) => {
  await acervoPaginado(page);
  await page.goto('/djen');
  await page.route('**/api/djen/acervo?**', async route => {
    if (new URL(route.request().url()).searchParams.get('page') !== '2') return route.fallback();
    await route.fulfill({ status: 500, json: { success: false, error: { message: 'Falha na segunda página.' } } });
  });
  await page.getByRole('checkbox', { name: 'Selecionar todas (3)', exact: true }).check();
  await page.getByRole('checkbox', { name: 'Selecionar publicação 98002' }).uncheck();
  const downloads = [];
  page.on('download', download => downloads.push(download));
  await page.getByRole('button', { name: 'Exportar selecionadas', exact: true }).click();
  await expect(page.getByText('Falha na segunda página.', { exact: true })).toBeVisible();
  await expect(page.getByText('2 selecionadas', { exact: true })).toBeVisible();
  await expect(page.getByRole('checkbox', { name: 'Selecionar publicação 98001' })).toBeChecked();
  await expect(page.getByRole('checkbox', { name: 'Selecionar publicação 98002' })).not.toBeChecked();
  expect(downloads).toHaveLength(0);
});

test('DJEN: selecionar mais de 16 mil é imediato e não consulta outras páginas', async ({ page }) => {
  const state = await acervoPaginado(page, 16001);
  await page.goto('/djen');
  await expect(page.getByRole('checkbox', { name: 'Selecionar todas (16001)', exact: true })).toBeVisible();
  const consultasIniciais = state.consultas.length;
  await page.getByRole('checkbox', { name: 'Selecionar todas (16001)', exact: true }).check();
  await expect(page.getByText('16001 selecionadas', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Exportar selecionadas', exact: true })).toBeEnabled();
  await page.getByRole('checkbox', { name: 'Selecionar publicação 98001' }).uncheck();
  await expect(page.getByText('16000 selecionadas', { exact: true })).toBeVisible();
  expect(state.consultas).toHaveLength(consultasIniciais);
  await page.getByRole('checkbox', { name: 'Selecionar publicação 98001' }).check();
  await expect(page.getByText('16001 selecionadas', { exact: true })).toBeVisible();
  await page.getByRole('checkbox', { name: 'Selecionar todas (16001)', exact: true }).uncheck();
  await expect(page.getByText('Nenhuma selecionada', { exact: true })).toBeVisible();
  expect(state.consultas).toHaveLength(consultasIniciais);
});

test('DJEN: importar seleção completa respeita exclusões e mudar filtros limpa seleção', async ({ page }) => {
  const state = await acervoPaginado(page);
  await page.goto('/djen');
  await page.getByRole('checkbox', { name: 'Selecionar todas (3)', exact: true }).check();
  await page.getByRole('checkbox', { name: 'Selecionar publicação 98002' }).uncheck();
  await importarSemParte(page);
  await expect.poll(() => state.actions.length).toBe(1);
  expect(state.actions[0].body.ids).toEqual([98001, 98003]);
  await page.getByRole('checkbox', { name: 'Selecionar todas (3)', exact: true }).check();
  await page.getByLabel('Número do processo', { exact: true }).fill('123');
  await expect(page).toHaveURL(/numero_processo=123/);
  await expect(page.getByText('Nenhuma selecionada', { exact: true })).toBeVisible();
});

test('DJEN: contexto permite edição com prévia e preserva versão enviada', async ({ page }) => {
  await acervoSetup(page);
  const ctx = {id:1,nome:'Contexto existente',descricao:'Objetivo inicial',versao:3,criterios:{tribunal:['TJMG']},nomes:[],tribunais:[],contagens:{relevante:100},pode_treinar:false,modelo:null};
  await page.route('**/api/djen/acervo?**', route => route.fulfill({json:{success:true,data:{items:[],total:0,page:1,per_page:20,contextos:[ctx]}}}));
  await page.route('**/api/djen/contextos/1/previa', route => route.fulfill({json:{success:true,data:{total:8,entram:2,saem:4,permanecem:6}}}));
  let corpo;
  await page.route('**/api/djen/contextos/1', route => {
    corpo = route.request().postDataJSON(); Object.assign(ctx, corpo, {versao:4});
    return route.fulfill({json:{success:true,data:ctx}});
  });
  await page.goto('/djen/classificacao?contexto_id=1&rotulo=');
  await page.getByRole('button',{name:'Editar contexto',exact:true}).click();
  const form = page.getByRole('form',{name:'Editar contexto'});
  await form.getByLabel('Nome do contexto',{exact:true}).fill('Novo objetivo');
  await form.getByRole('button',{name:'Conferir contexto'}).click();
  await expect(form.getByRole('status')).toContainText('2 entram, 4 saem, 6 permanecem');
  await form.getByRole('button',{name:'Salvar contexto'}).click();
  await expect(page.getByRole('combobox',{name:'Contexto de classificação',exact:true})).toContainText('Novo objetivo');
  expect(corpo.versao).toBe(3);
  expect(corpo.criterios.tribunal).toEqual(['TJMG']);
});

test('DJEN: treinamento mostra progresso real, log, algoritmo, bases e métricas', async ({ page }) => {
  await acervoSetup(page);
  const ctx={id:1,nome:'Treino auditável',nomes:[],tribunais:[],versao:2,contagens:{relevante:120,irrelevante:120},pode_treinar:true,modelo:null,treino_status:'executando'};
  const execucao={id:7,contexto_id:1,status:'executando',etapa:'Treinar modelo de avaliação',etapas_concluidas:3,solicitado_em:'2026-11-18T10:00:00',iniciado_em:'2026-11-18T10:00:01',finalizado_em:null,contexto_snapshot:{nome:'Treino auditável',versao:2,avaliacoes_versao:240,criterios:{tribunal:['TJMG']}},logs:[{horario:'2026-11-18T10:00:03',etapa:'Treinar modelo de avaliação',mensagem:'TF-IDF preparado com 100 atributos.'}],metricas:{},modelo_id:null,erro:null};
  await page.route('**/api/djen/contextos',route=>route.fulfill({json:{success:true,data:[ctx]}}));
  await page.route('**/api/djen/acervo?**',route=>route.fulfill({json:{success:true,data:{items:[],total:0,page:1,per_page:20,contextos:[ctx]}}}));
  await page.route('**/api/djen/contextos/1/treinos?**',route=>route.fulfill({json:{success:true,data:{items:[execucao],total:1,page:1,per_page:20}}}));
  await page.goto('/djen/classificacao?contexto_id=1&rotulo=');
  await expect(page.getByRole('progressbar')).toHaveAttribute('value','3');
  await expect(page.getByText(/TF-IDF preparado com 100 atributos/)).toBeVisible();
  await expect(page.getByRole('button',{name:'Editar contexto',exact:true})).toBeDisabled();
  Object.assign(execucao,{status:'concluido',etapa:'Concluído',etapas_concluidas:7,finalizado_em:'2026-11-18T10:00:10',modelo_id:9,metricas:{algoritmo:'TF-IDF + regressão logística',total:240,processos:60,classes:{relevante:120,irrelevante:120},origens:{classificacao:240},excluidos:{sem_texto:2,sem_processo:0},bases:{treino:{exemplos:180,processos:45,relevantes:90,irrelevantes:90},validacao:{exemplos:60,processos:15,relevantes:30,irrelevantes:30}},precisao:0.9,revocacao:0.9,f1:0.9,matriz_confusao:[[27,3],[3,27]],parametros:{max_iter:1000}}});
  ctx.treino_status='concluido';
  await expect(page.getByRole('progressbar')).toHaveAttribute('value','7',{timeout:10000});
  await expect(page.getByText(/TF-IDF \+ regressão logística/)).toBeVisible();
  await expect(page.getByRole('table',{name:'Divisão dos exemplos'})).toContainText('180');
  await expect(page.getByRole('table',{name:'Divisão dos exemplos'})).toContainText('25.0%');
  await expect(page.getByRole('table',{name:'Matriz de confusão'})).toContainText('3 falsos positivos');
  await expect(page.getByRole('button',{name:'Editar contexto',exact:true})).toBeEnabled();
  await page.setViewportSize({width:390,height:844});
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'/tmp/djen-treino-painel-mobile.png',fullPage:true});
});

 test('DJEN: treino distingue vínculo operacional de avaliação no contexto', async ({page}) => {
 const state = await acervoSetup(page);
 Object.assign(state.items[0], {situacao:'vinculada',comunicacao_id:12,id_processo:71,rotulo:'nao_classificado'});
 await page.goto('/djen/classificacao?contexto_id=1&rotulo=');
 await expect(page.getByText('Vinculada ao processo',{exact:true})).toBeVisible();
 await expect(page.getByText('Não avaliada neste contexto',{exact:true}).first()).toBeVisible();
 await page.getByText('Detalhes e histórico',{exact:true}).first().click();
 await expect(page.getByRole('link',{name:'Processo #71'})).toHaveAttribute('href','/processos/71');
 expect(state.errors).toEqual([]);
 });

test('DJEN: criar contexto preserva formulário em erro e exclui filtros de revisão', async ({page}) => {
 const state = await acervoSetup(page); const pedidos=[];
 await page.route('**/api/djen/contextos', async route => {
  if(route.request().method() === 'GET') return route.fallback();
  const body=route.request().postDataJSON(); pedidos.push(body);
  if(pedidos.length === 1) return route.fulfill({status:400,json:{success:false,error:{message:'Nome já usado'}}});
  return route.fulfill({json:{success:true,data:{id:2,...body}}});
 });
 await page.goto('/djen/classificacao?contexto_id=1&rotulo=nao_classificado&situacao=vinculada&sugestao=sem_sugestao&oab=123MG');
 await page.getByRole('button',{name:'Criar contexto',exact:true}).click();
 const form=page.getByRole('form',{name:'Criar contexto'});
 await form.getByLabel('Nome do contexto',{exact:true}).fill('Novo contexto');
 await form.getByLabel('Descrição',{exact:true}).fill('Objetivo');
 await form.getByRole('button',{name:'Salvar contexto'}).click();
 await expect(form.getByRole('alert')).toBeVisible();
 await expect(form.getByLabel('Nome do contexto',{exact:true})).toHaveValue('Novo contexto');
 expect(pedidos[0].criterios).toEqual({oab:'123MG',tribunal:[]});
 await form.getByRole('button',{name:'Salvar contexto'}).click();
 await expect(page).toHaveURL(/contexto_id=2/);
 for(const key of ['situacao','sugestao']) expect(new URL(page.url()).searchParams.has(key)).toBe(false);
 expect(new URL(page.url()).searchParams.get('rotulo')).toBe('nao_classificado');
 await page.getByRole('button',{name:'Criar contexto',exact:true}).click();
 await page.getByRole('form',{name:'Criar contexto'}).getByRole('button',{name:'Cancelar',exact:true}).click();
 await expect(page.getByRole('form',{name:'Criar contexto'})).toHaveCount(0);
 expect(pedidos).toHaveLength(2);
 expect(state.errors).toEqual([]);
});

test('DJEN: texto integral e classificação rápida independem dos checkboxes', async ({page}) => {
 const state = await acervoSetup(page);
 state.items[0].texto_plano = 'Texto longo da publicação.\n'.repeat(60) + 'Último parágrafo integral <script>texto seguro</script>';
 state.items[0].partes=['Parte autora','Parte ré'];
 let pediuTexto=false;
 page.on('request', req => { const url=new URL(req.url()); if(url.pathname.endsWith('/acervo') && url.searchParams.get('texto_integral')==='1') pediuTexto=true; });
 await page.goto('/djen/classificacao?contexto_id=1&rotulo=');
 await expect(page.getByLabel('Texto integral da publicação').first()).toHaveText(state.items[0].texto_plano);
 await expect(page.getByText('Parte autora · Parte ré',{exact:false})).toBeVisible();
 expect(pediuTexto).toBe(true);
 await expect(page.getByRole('button',{name:'Relevante',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'Marcar publicação 98001 como relevante',exact:true}).click();
 await expect(page.getByText('Relevante neste contexto',{exact:true})).toBeVisible();
 expect(state.actions[0]).toMatchObject({path:'/api/djen/contextos/1/classificar',body:{ids:[98001],rotulo:'relevante'}});
 await page.getByRole('button',{name:'Marcar publicação 98001 como irrelevante',exact:true}).click();
 await expect(page.getByText('Irrelevante neste contexto',{exact:true})).toBeVisible();
 expect(state.actions[1].body).toMatchObject({ids:[98001],rotulo:'irrelevante'});
 await page.getByRole('checkbox',{name:'Selecionar publicação 98001'}).check();
 await expect(page.getByRole('heading',{name:'Classificar selecionadas (1)'})).toBeVisible();
 await page.getByRole('button',{name:'Não analisado',exact:true}).click();
 expect(state.actions[2].body).toMatchObject({ids:[98001],rotulo:'nao_classificado'});
 await page.setViewportSize({width:390,height:844});
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
 await page.screenshot({path:'/tmp/gl-classificacao-cards.png',fullPage:true});
 await page.goto('/djen/classificacao');
 await expect(page.getByRole('button',{name:'Marcar publicação 98001 como relevante',exact:true})).toBeDisabled();
 expect(state.errors).toEqual([]);
});

test('DJEN: variações dos nomes acompanham filtros e criação sem misturar revisão', async ({page}) => {
 const state=await acervoSetup(page); let corpo;
 await page.route('**/api/djen/contextos', async route => {
  if(route.request().method()==='GET') return route.fallback();
  corpo=route.request().postDataJSON(); return route.fulfill({json:{success:true,data:{id:2,...corpo}}});
 });
 await page.goto('/djen/classificacao?contexto_id=1&rotulo=');
 await page.getByLabel('Nome da parte',{exact:true}).fill('UFMG');
 await page.getByLabel('Variações do nome',{exact:true}).fill('Universidade Federal de Minas Gerais; Universidade Mineira');
 await expect.poll(()=>new URL(page.url()).searchParams.getAll('nomes')).toEqual(['Universidade Federal de Minas Gerais','Universidade Mineira']);
 await page.getByRole('combobox',{name:'Situação operacional',exact:true}).click();
 await expect(page.getByRole('option',{name:'Pendente de vinculação',exact:true})).toBeVisible();
 await expect(page.getByRole('option',{name:'Não analisado',exact:true})).toHaveCount(0);
 await page.getByRole('option',{name:'Vinculada ao processo',exact:true}).click();
 await expect.poll(()=>new URL(page.url()).searchParams.get('situacao_operacional')).toBe('vinculada');
 await page.getByRole('combobox',{name:'Avaliação neste contexto',exact:true}).click();
 await page.getByRole('option',{name:'Não analisado',exact:true}).click();
 await expect.poll(()=>new URL(page.url()).searchParams.get('rotulo')).toBe('nao_classificado');
 await page.getByRole('button',{name:'Criar contexto',exact:true}).click();
 const form=page.getByRole('form',{name:'Criar contexto'});
 await form.getByLabel('Nome do contexto',{exact:true}).fill('Universidade');
 await form.getByRole('button',{name:'Salvar contexto'}).click();
 await expect(page).toHaveURL(/contexto_id=2/);
 expect(corpo.criterios).toEqual({nomes:['UFMG','Universidade Federal de Minas Gerais','Universidade Mineira'],tribunal:[]});
 // Decisão de 20/11/2026: após criar, a fila abre limpa; os critérios ficam só no contexto.
 expect(Object.fromEntries(new URL(page.url()).searchParams)).toEqual({per_page:'20',contexto_id:'2',rotulo:'nao_classificado'});
 expect(new URL(page.url()).searchParams.has('situacao_operacional')).toBe(false);
 await page.setViewportSize({width:390,height:844});
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 expect(state.errors).toEqual([]);
});

test('DJEN: detalhes no rodapé carregam ao expandir e permitem repetir em falha', async ({page}) => {
 const state=await acervoSetup(page); let consultas=0;
 await page.route('**/api/djen/acervo/1',route=>{
  consultas++;
  if(consultas===1) return route.fulfill({status:503,json:{success:false,error:{message:'Falha temporária'}}});
  return route.fulfill({json:{success:true,data:{...state.items[0],capturada_em:'2026-11-20T10:00:00',atualizada_em:'2026-11-20T11:00:00',oab_origem:'123/MG',link:'javascript:alert(1)',link_certidao:'https://tribunal.exemplo.invalid/certidao',advogados:[{nome:'Advogada',numero_oab:'123',uf_oab:'MG'}],historico:[{contexto_nome:'Contexto fictício',rotulo_anterior:'nao_classificado',rotulo:'relevante',rotulado_em:'2026-11-20T11:00:00',origem:'classificacao',id_rotulado_por:1}]}}});
 });
 await page.goto('/djen/classificacao?contexto_id=1&rotulo=');
 expect(consultas).toBe(0);
 await expect(page.getByRole('link',{name:'Ler publicação e histórico'})).toHaveCount(0);
 const resumo=page.getByText('Detalhes e histórico',{exact:true}).first();
 await resumo.click();
 await expect(page.getByRole('alert')).toContainText('Falha temporária');
 await page.getByRole('button',{name:'Tentar novamente'}).click();
 await expect(page.getByText('123/MG',{exact:true})).toBeVisible();
 await expect(page.getByRole('heading',{name:'Histórico da classificação'})).toBeVisible();
 await expect(page.getByText(/Não avaliada → Relevante/)).toBeVisible();
 await expect(page.getByRole('link',{name:'Documento no tribunal'})).toHaveCount(0);
 await expect(page.getByRole('link',{name:'Certidão do DJEN (PDF)'})).toHaveAttribute('rel','noopener noreferrer');
 await page.getByRole('button',{name:'Marcar publicação 98001 como relevante',exact:true}).click();
 await expect.poll(()=>consultas).toBe(3);
 await resumo.click();
 await expect(page.getByRole('heading',{name:'Histórico da classificação'})).not.toBeVisible();
 await expect(page).toHaveURL(/classificacao/);
 expect(state.errors).toEqual([]);
});

test('DJEN: botões desativados explicam o motivo apenas no hover', async ({page}) => {
 await acervoSetup(page);
 await page.goto('/djen/classificacao');
 await expect(page.getByRole('tooltip')).toHaveCount(0);
 await expect(page.getByText('Selecione ou crie um contexto para classificar.',{exact:true})).not.toBeVisible();
 await page.getByRole('button',{name:'Marcar publicação 98001 como relevante',exact:true}).hover();
 await expect(page.getByRole('tooltip')).toContainText('Selecione ou crie um contexto');
 await page.goto('/djen/classificacao?contexto_id=1&rotulo=');
 await page.getByRole('button',{name:'Relevante',exact:true}).hover();
 await expect(page.getByRole('tooltip')).toContainText('Marque os checkboxes');
 await page.getByRole('checkbox',{name:'Selecionar publicação 98001'}).check();
 await page.getByRole('button',{name:'Relevante',exact:true}).hover();
 await expect(page.getByRole('tooltip')).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Relevante',exact:true})).toBeEnabled();
});

test('DJEN: ajuda das variações fica no tooltip e os campos ficam alinhados', async ({page}) => {
 await acervoSetup(page);
 await page.setViewportSize({width:1440,height:1000});
 await page.goto('/djen/classificacao');
 const nome=await page.getByLabel('Nome da parte',{exact:true}).boundingBox();
 const variacoes=await page.getByLabel('Variações do nome',{exact:true}).boundingBox();
 expect(Math.abs((nome.y+nome.height)-(variacoes.y+variacoes.height))).toBeLessThan(2);
 expect(Math.abs(nome.height-variacoes.height)).toBeLessThan(2);
 await expect(page.getByRole('tooltip')).toHaveCount(0);
 await page.getByRole('button',{name:'Como informar variações do nome'}).hover();
 await expect(page.getByRole('tooltip')).toContainText('Separe por ponto e vírgula');
 await page.getByRole('heading',{name:'Acervo para treino'}).hover();
 await expect(page.getByRole('tooltip')).toHaveCount(0);
 await page.getByRole('region',{name:'Filtros de publicações'}).screenshot({path:'/tmp/gl-filtros-alinhados.png'});
});

test('DJEN: card identifica polos das partes e aplica filtros automaticamente', async ({page}) => {
 const state=await acervoSetup(page);
 state.items[0].partes_com_polo=[{nome:'Autora fictícia',polo:'A'},{nome:'Ré fictícia',polo:'P'},{nome:'Terceiro',polo:null}];
 await page.goto('/djen/classificacao');
 const partes=page.getByLabel('Partes da publicação').first();
 await expect(partes).toContainText('Polo ativo: Autora fictícia');
 await expect(partes).toContainText('Polo passivo: Ré fictícia');
 await expect(partes).toContainText('Polo não informado: Terceiro');
 await expect(page.getByRole('button',{name:'Filtrar',exact:true})).toHaveCount(0);
 await page.getByLabel('Nome da parte',{exact:true}).fill('Autora');
 await expect.poll(()=>new URL(page.url()).searchParams.get('nome_parte')).toBe('Autora');
 expect(state.errors).toEqual([]);
});

test('DJEN: excluir contexto exige confirmação e preserva acervo após erro recuperável', async ({page}) => {
 const state=await acervoSetup(page); let excluido=false; let pedidos=0;
 const ctx={id:1,nome:'Contexto para excluir',criterios:{},nomes:[],tribunais:[],versao:1,contagens:{},pode_treinar:false,modelo:null,treino_status:'ocioso'};
 await page.route('**/api/djen/acervo?**',route=>route.fulfill({json:{success:true,data:{items:state.items,total:2,page:1,per_page:20,contextos:excluido?[]:[ctx]}}}));
 await page.route('**/api/djen/contextos/1',route=>{
  expect(route.request().method()).toBe('DELETE'); pedidos++;
  if(pedidos===1) return route.fulfill({status:503,json:{success:false,error:{message:'Falha temporária'}}});
  excluido=true; return route.fulfill({json:{success:true,data:{excluido:true}}});
 });
 await page.goto('/djen/classificacao?contexto_id=1&oab=123MG');
 await page.getByRole('button',{name:'Editar contexto',exact:true}).click();
 await page.getByRole('button',{name:'Excluir contexto',exact:true}).click();
 const modal=page.getByRole('alertdialog');
 await expect(modal).toContainText('Cuidado: esta operação não pode ser desfeita.');
 await expect(modal).toContainText('As publicações, processos, casos e os demais contextos serão preservados.');
 await modal.getByRole('button',{name:'Cancelar',exact:true}).click();
 expect(pedidos).toBe(0);
 await page.getByRole('button',{name:'Excluir contexto',exact:true}).click();
 await modal.getByRole('button',{name:'Excluir definitivamente'}).click();
 await expect(modal.getByRole('alert')).toContainText('Falha temporária');
 await modal.getByRole('button',{name:'Excluir definitivamente'}).click();
 await expect.poll(()=>new URL(page.url()).searchParams.has('contexto_id')).toBe(false);
 expect(new URL(page.url()).searchParams.get('oab')).toBe('123MG');
 await expect(page.getByRole('checkbox',{name:'Selecionar publicação 98001'})).toBeVisible();
 await expect(page.getByRole('checkbox',{name:'Selecionar publicação 98002'})).toBeVisible();
 await expect(page.getByRole('button',{name:'Editar contexto',exact:true})).toHaveCount(0);
 expect(pedidos).toBe(2);
 expect(state.errors).toEqual([]);
});

test('DJEN: nome sugerido usa critérios e mantém a edição manual', async ({page}) => {
 await acervoSetup(page);
 await page.goto('/djen/classificacao?nome_parte=UFMG&nomes=Universidade+Federal&tribunal=TJMG&polo=P&situacao_operacional=vinculada');
 await page.getByRole('button',{name:'Criar contexto',exact:true}).click();
 const form=page.getByRole('form',{name:'Criar contexto'});
 await expect(form.getByLabel('Nome do contexto',{exact:true})).toHaveValue('UFMG (+1 variação) · TJMG · Polo passivo · Sem intervalo de tempo');
 await form.getByLabel('Nome do contexto',{exact:true}).fill('Meu contexto');
 await page.getByLabel('OAB',{exact:true}).fill('123MG');
 await expect.poll(()=>new URL(page.url()).searchParams.get('oab')).toBe('123MG');
 await expect(form.getByLabel('Nome do contexto',{exact:true})).toHaveValue('Meu contexto');
 await form.getByRole('button',{name:'Cancelar',exact:true}).click();
 await page.getByRole('button',{name:'Limpar filtros',exact:true}).click();
 await expect.poll(()=>new URL(page.url()).searchParams.has('nome_parte')).toBe(false);
 await page.getByRole('button',{name:'Criar contexto',exact:true}).click();
 await expect(page.getByLabel('Nome do contexto',{exact:true})).toHaveValue('Publicações da unidade · Sem intervalo de tempo');
});


test('DJEN: classificação rápida confirma antes de recolher e permite desfazer', async ({page}) => {
 const state = await acervoSetup(page);
 await page.goto('/djen/classificacao?contexto_id=1&rotulo=nao_classificado');
 const card = page.locator('li').filter({has:page.getByRole('checkbox',{name:'Selecionar publicação 98001',exact:true})});
 await page.getByRole('button',{name:'Marcar publicação 98001 como relevante',exact:true}).click();
 await expect(card.getByText('Relevante neste contexto',{exact:true})).toBeVisible();
 await expect(card).toHaveClass(/border-green-600/);
 await expect(page.getByRole('button',{name:'Marcar publicação 98001 como relevante',exact:true})).toBeDisabled();
 await expect(card).toHaveCount(0);
 await expect(page.getByText('1 publicações encontradas.',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Desfazer',exact:true}).click();
 await expect(card).toBeVisible();
 await expect(card.getByText('Não avaliada neste contexto',{exact:true})).toBeVisible();
 // Desfazer pede a reversão ao servidor; reenviar o rótulo gravaria nova avaliação manual.
 expect(state.actions).toEqual([
  {path:'/api/djen/contextos/1/classificar',body:{ids:[98001],rotulo:'relevante'}},
  {path:'/api/djen/contextos/1/desfazer',body:{historico_id:1}}
 ]);
 expect(state.errors).toEqual([]);
});

test('DJEN: trocar de contexto abre a fila sem herdar filtros', async ({page}) => {
 const state = await acervoSetup(page);
 const contextos=[{id:1,nome:'Contexto fictício',nomes:['Parte Teste'],tribunais:[],contagens:{},pode_treinar:false,modelo:null},{id:2,nome:'Outro contexto',nomes:['Beta'],tribunais:[],contagens:{},pode_treinar:false,modelo:null}];
 await page.route('**/api/djen/acervo?*', route => route.fulfill({json:{success:true,data:{items:state.items,total:2,page:1,per_page:50,contextos}}}));
 await page.goto('/djen/classificacao?nome_parte=Alfa&inicio=2026-01-01&situacao_operacional=descartada&per_page=50&page=2&contexto_id=1&rotulo=relevante');
 await page.getByRole('combobox',{name:'Contexto de classificação',exact:true}).click();
 await page.getByRole('option',{name:'Outro contexto',exact:true}).click();
 await expect(page).toHaveURL(/contexto_id=2/);
 expect(Object.fromEntries(new URL(page.url()).searchParams)).toEqual({per_page:'50',contexto_id:'2',rotulo:'nao_classificado'});
 await expect(page.getByLabel('Nome da parte',{exact:true})).toHaveValue('');
 expect(state.errors).toEqual([]);
});

test('DJEN: falha na classificação rápida mantém card e permite nova tentativa', async ({page}) => {
 const state = await acervoSetup(page);
 await page.route('**/api/djen/contextos/1/classificar', route => route.fulfill({status:503,json:{success:false,error:{message:'Falha ao salvar teste'}}}));
 await page.goto('/djen/classificacao?contexto_id=1&rotulo=nao_classificado');
 const botao=page.getByRole('button',{name:'Marcar publicação 98001 como irrelevante',exact:true});
 await botao.click();
 await expect(page.getByText('Falha ao salvar teste',{exact:true})).toBeVisible();
 await expect(botao).toBeEnabled();
 await expect(page.getByRole('checkbox',{name:'Selecionar publicação 98001',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Desfazer',exact:true})).toHaveCount(0);
 expect(state.items[0].rotulo).toBe('nao_classificado');
 expect(state.errors).toEqual([]);
});

test('DJEN: selecionar contexto inicia fila de não avaliadas', async ({page}) => {
 await acervoSetup(page);
 await page.goto('/djen/classificacao');
 await page.getByRole('combobox',{name:'Contexto de classificação',exact:true}).click();
 await page.getByRole('option',{name:'Contexto fictício',exact:true}).click();
 await expect(page).toHaveURL(/rotulo=nao_classificado/);
 expect(new URL(page.url()).searchParams.get('contexto_id')).toBe('1');
});


test('DJEN: abrir contexto sem filtro inicia fila e oculta classificação rápida', async ({page}) => {
 const state = await acervoSetup(page);
 await page.goto('/djen/classificacao?contexto_id=1');
 await expect(page).toHaveURL(/rotulo=nao_classificado/);
 await expect(page.getByRole('combobox',{name:'Avaliação neste contexto',exact:true})).toHaveText('Não analisado');
 await page.getByRole('button',{name:'Marcar publicação 98001 como relevante',exact:true}).click();
 await expect(page.getByText('Relevante neste contexto',{exact:true})).toBeVisible();
 await expect(page.getByRole('checkbox',{name:'Selecionar publicação 98001',exact:true})).toHaveCount(0);
 await page.getByRole('combobox',{name:'Avaliação neste contexto',exact:true}).click();
 await page.getByRole('option',{name:'Todas',exact:true}).click();
 await expect(page.getByRole('checkbox',{name:'Selecionar publicação 98001',exact:true})).toBeVisible();
 expect(new URL(page.url()).searchParams.get('rotulo')).toBe('');
 await page.reload();
 await expect(page.getByRole('combobox',{name:'Avaliação neste contexto',exact:true})).toHaveText('Todas');
 await expect(page.getByRole('checkbox',{name:'Selecionar publicação 98001',exact:true})).toBeVisible();
 expect(state.errors).toEqual([]);
});
