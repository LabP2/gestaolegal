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
        page.getByRole("button", { name: "Situação do Deferimento" }),
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
                /^\$app\/environment$|^\$env\/dynamic\/public$|^\.\/stores\/unidade$/,
            },
            (args) => ({ path: args.path, namespace: "teste" }),
          );
          build.onLoad({ filter: /.*/, namespace: "teste" }, (args) => ({
            contents:
              args.path === "$app/environment"
                ? "export const dev = false;"
                : args.path === "$env/dynamic/public"
                  ? "export const env = {};"
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
