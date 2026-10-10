import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash, randomBytes } from 'node:crypto';
import { chromium } from 'playwright';

const base = 'https://localhost:19443';
const issuer = process.env.TEST_ISSUER;
const browser = await chromium.launch({...(process.env.TEST_CHROME ? {executablePath:process.env.TEST_CHROME} : {}), headless:true, args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const context = await browser.newContext({ignoreHTTPSErrors:true, viewport:{width:1024,height:768}});
const failures = [];
const capture = page => {
    const sessions = [];
    page.on('pageerror', error => failures.push(error.message));
    page.on('websocket', ws => ws.on('framereceived', ({payload}) => {
        const frame = JSON.parse(payload.toString());
        if(frame.type === 'session') sessions.push(frame);
    }));
    return sessions;
};
const waitFor = async predicate => {
    for(let i=0;i<100;i++) {
        if(predicate()) return;
        await new Promise(resolve=>setTimeout(resolve,100));
    }
    throw new Error('Timed out waiting for session');
};
const host = config => {
    const result = spawnSync(process.env.TEST_PYTHON,[process.env.TEST_HOST_SCRIPT],{input:JSON.stringify(config),encoding:'utf8'});
    assert.equal(result.status,0,result.stderr);
    return JSON.parse(result.stdout.trim().split('\n').at(-1));
};
try {
    const page = await context.newPage();
    const tokenSessions = capture(page);
    await page.goto(base);
    await page.waitForTimeout(3000);
    await page.screenshot({path:'/tmp/oauth-dual-choice.png'});
    await page.mouse.click(512,405);
    await waitFor(()=>tokenSessions.length);
    const token = tokenSessions[0];
    assert.ok(!token.authMethod);
    assert.ok(token.mcpToken.startsWith('mcp-'));
    await page.mouse.click(512,421);
    await page.waitForTimeout(500);
    await page.screenshot({path:'/tmp/oauth-token-options.png'});
    const tokenResult = host({url:token.mcpUrl,token:token.mcpToken,name:'TokenSmoke'});
    const oauthPage = await context.newPage();
    const oauthSessions = capture(oauthPage);
    await oauthPage.goto(base);
    await oauthPage.waitForTimeout(5000);
    await oauthPage.mouse.click(512,465);
    await oauthPage.waitForTimeout(1500);
    await oauthPage.screenshot({path:'/tmp/oauth-after-select.png'});
    await oauthPage.locator('input[name=username]').fill('alice');
    await oauthPage.locator('input[name=password]').fill('strong-local-password');
    const loginResponse = oauthPage.waitForResponse(r => new URL(r.url()).pathname === '/oauth/login' && r.request().method() === 'POST');
    await oauthPage.getByRole('button',{name:'Create account'}).click();
    const logged = await loginResponse;
    assert.equal(logged.status(),303,'Login origin: '+logged.request().headers()['origin']);
    await oauthPage.getByRole('button',{name:'Allow',exact:true}).click();
    await oauthPage.waitForURL(base+'/?auth=oauth');
    await oauthPage.waitForTimeout(5000);
    await oauthPage.mouse.click(512,465);
    await waitFor(()=>oauthSessions.length);
    const oauth = oauthSessions[0];
    assert.equal(oauth.authMethod,'oauth');
    assert.ok(oauth.mcpUrl.startsWith(base+'/mcp/'));
    assert.ok(!('mcpToken' in oauth));
    await oauthPage.mouse.click(512,421);
    await oauthPage.waitForTimeout(500);
    await oauthPage.screenshot({path:'/tmp/oauth-connect-options.png'});
    const verifier = randomBytes(48).toString('base64url');
    const challenge = createHash('sha256').update(verifier).digest('base64url');
    const state = randomBytes(24).toString('base64url');
    const hostPage = await context.newPage();
    const registeredResponse = await context.request.post(issuer+'/oauth/register',{data:{redirect_uris:[issuer+'/oauth/host-callback'],client_name:'Local MCP host'}});
    assert.equal(registeredResponse.status(),201);
    const registered = await registeredResponse.json();
    const authorize = new URL(issuer+'/oauth/authorize');
    authorize.search = new URLSearchParams({response_type:'code',client_id:registered.client_id,redirect_uri:issuer+'/oauth/host-callback',scope:'openid mcp:access',state,resource:base+'/mcp',code_challenge:challenge,code_challenge_method:'S256'}).toString();
    await hostPage.goto(authorize.href);
    await hostPage.getByRole('button',{name:'Allow',exact:true}).click();
    await hostPage.waitForURL(issuer+'/oauth/host-callback?**');
    const callback = new URL(hostPage.url());
    assert.equal(callback.searchParams.get('state'),state);
    assert.equal(callback.searchParams.get('iss'),issuer);
    const fields = {grant_type:'authorization_code',client_id:registered.client_id,redirect_uri:issuer+'/oauth/host-callback',code:callback.searchParams.get('code'),code_verifier:verifier,resource:base+'/mcp'};
    const response = await context.request.post(issuer+'/oauth/token',{form:fields});
    assert.equal(response.status(),200);
    const credentials = await response.json();
    assert.equal(credentials.scope, 'mcp:access openid');
    assert.ok(credentials.id_token);
    if (process.env.TEST_INSPECTOR_VERSION) {
        const inspected = spawnSync('npx', ['--yes', '@modelcontextprotocol/inspector@'+process.env.TEST_INSPECTOR_VERSION, '--cli', oauth.mcpUrl, '--transport', 'http', '--method', 'tools/list', '--format', 'json', '--header', 'Authorization: Bearer '+credentials.access_token], {encoding:'utf8', env:{...process.env, NODE_EXTRA_CA_CERTS:process.env.TEST_CERTIFICATE, MCP_STORAGE_DIR:process.env.TEST_STORAGE_DIR, MCP_CATALOG_PATH:process.env.TEST_STORAGE_DIR+'/catalog.json'}, timeout:120000});
        assert.equal(inspected.status, 0, inspected.stderr);
        assert.equal(JSON.parse(inspected.stdout).result.tools.length, 10);
    }
    const replay = await context.request.post(issuer+'/oauth/token',{form:fields});
    assert.equal(replay.status(),400);
    const oauthResult = host({url:oauth.mcpUrl,token:credentials.access_token,name:'OAuthSmoke'});
    const refreshResponse = await context.request.post(issuer+'/oauth/token',{form:{client_id:registered.client_id,grant_type:'refresh_token',refresh_token:credentials.refresh_token,resource:base+'/mcp'}});
    assert.equal(refreshResponse.status(),200);
    const renewed = await refreshResponse.json();
    assert.notEqual(renewed.refresh_token,credentials.refresh_token);
    assert.equal(host({url:oauth.mcpUrl,token:renewed.access_token,name:null}).player.id,oauthResult.player.id);
    assert.equal(tokenResult.move, true);
    assert.equal(oauthResult.move, true);
    assert.notDeepEqual(tokenResult.player,oauthResult.player);
    await oauthPage.waitForTimeout(1500);
    await oauthPage.screenshot({path:'/tmp/oauth-game.png'});
    await page.screenshot({path:'/tmp/token-game.png'});
    const logoutResponse = oauthPage.waitForResponse(response => new URL(response.url()).pathname === '/app/oauth/logout');
    await oauthPage.mouse.click(889,727);
    assert.equal((await logoutResponse).status(),200);
    const denied = await context.request.post(base+'/mcp',{headers:{Authorization:'Bearer '+credentials.access_token},data:{jsonrpc:'2.0',id:1,method:'tools/list'}});
    assert.equal(denied.status(),401);
    const beforeSwitch = oauthSessions.length;
    await oauthPage.mouse.click(512,420);
    await waitFor(()=>oauthSessions.length > beforeSwitch);
    const switched = oauthSessions.at(-1);
    assert.equal(switched.mcpToken,token.mcpToken);
    assert.ok(!switched.authMethod);
    const stillToken = host({url:token.mcpUrl,token:token.mcpToken,name:null});
    assert.ok(JSON.stringify(stillToken.player).includes('TokenSmoke'));
    assert.equal(failures.length,0,failures.join('\n'));
    console.log(JSON.stringify({embedded:true,openid:true,inspector:!!process.env.TEST_INSPECTOR_VERSION,registration:true,refresh:true,dual:true,token:tokenResult.login,oauth:oauthResult.login,tools:oauthResult.tools,tokenMoved:tokenResult.move,oauthMoved:oauthResult.move,codeReplayRejected:true,logoutRevoked:true,switchToToken:true,tokenUnaffected:true,browserErrors:failures.length}));
} finally {
    await browser.close();
}
