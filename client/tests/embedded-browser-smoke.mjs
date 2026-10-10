import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash, randomBytes } from 'node:crypto';
import { chromium } from 'playwright';

const base = 'https://localhost:19443';
const issuer = process.env.TEST_ISSUER;
const callbackOrigin = 'https://127.0.0.1:19470';
const redirect = callbackOrigin + '/connector_platform_oauth_redirect';
const browser = await chromium.launch({...(process.env.TEST_CHROME ? {executablePath:process.env.TEST_CHROME} : {}), headless:true, args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const context = await browser.newContext({ignoreHTTPSErrors:true, viewport:{width:1024,height:768}, permissions:["clipboard-read","clipboard-write"]});
const failures = [];
const browserRequests = [];
const unauthenticatedConsent = [];
const unauthenticatedResponses = [];
const analyticsRequests = [];
const watchAnalytics = context => context.route('https://www.googletagmanager.com/**', async route => {
    analyticsRequests.push(route.request().url());
    await route.fulfill({contentType:'application/javascript',body:''});
});
await watchAnalytics(context);
const capture = page => {
    const sessions = [];
    page.on('pageerror', error => failures.push(error.message));
    page.on('console', message => {
        if (message.type() !== 'error') return;

        if (message.location().url === base + '/app/oauth/consent' && message.text().includes('403')) {
            unauthenticatedConsent.push(message.text());
            return;
        }

        failures.push(message.text());
    });
    page.on('response', response => {
        const path = new URL(response.url()).pathname;

        if (path.startsWith('/app/oauth/')) {
            browserRequests.push({path,method:response.request().method(),status:response.status()});
        }

        if (response.url() === base + '/app/oauth/consent' && response.request().method() === 'POST' && response.status() === 403) {
            unauthenticatedResponses.push(response.status());
        }
    });
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
    throw new Error('Timed out waiting for session: '+JSON.stringify({browserRequests,failures}));
};
let menuCaptures = 0;
const gameReady = async page => {
    await page.waitForLoadState('networkidle');
    await page.locator('#game[aria-busy=false] canvas').waitFor({state:'visible'});
    await page.evaluate(async () => {
        await document.fonts.ready;
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    });
    await page.screenshot({path:`/tmp/oauth-game-menu-${++menuCaptures}-connect.png`});
};
const checkAuthorizationLayout = async (page, name) => {
    assert.equal(await page.evaluate(() => getComputedStyle(document.documentElement).colorScheme), 'dark');

    for (const [size, width, height] of [['desktop', 1440, 900], ['mobile', 390, 844], ['small', 320, 568], ['landscape', 844, 390]]) {
        await page.setViewportSize({width, height});
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);

        for (const control of await page.locator('input:not([type=hidden]), button').all()) {
            assert.ok((await control.boundingBox()).height >= 44);
        }

        await page.screenshot({path: `/tmp/oauth-game-${name}-${size}.png`, fullPage: true});
    }

    await page.setViewportSize({width: 1024, height: 768});
};

const host = config => {
    const result = spawnSync(process.env.TEST_PYTHON,[process.env.TEST_HOST_SCRIPT],{input:JSON.stringify(config),encoding:'utf8'});
    assert.equal(result.status,0,result.stderr);
    return JSON.parse(result.stdout.trim().split('\n').at(-1));
};
try {
    const hostContext = await browser.newContext({ignoreHTTPSErrors:true, viewport:{width:1024,height:768}});
    await watchAnalytics(hostContext);
    const hostFirstPage = await hostContext.newPage();
    const hostFirstSessions = capture(hostFirstPage);
    const joinedPlayers = [];
    hostFirstPage.on('websocket', socket => socket.on('framereceived', ({payload}) => {
        const frame = JSON.parse(payload.toString());
        if (frame.type === 'login') joinedPlayers.push(frame.player.id);
    }));
    const initial = await hostContext.request.get(base + '/mcp');
    assert.equal(initial.status(), 401);
    const metadataUrl = initial.headers()['www-authenticate'].match(/resource_metadata="([^"]+)"/)[1];
    const metadata = await (await hostContext.request.get(metadataUrl)).json();
    assert.equal(metadata.resource, base + '/mcp');
    assert.ok(metadata.authorization_servers.includes(issuer));
    const discovery = await (await hostContext.request.get(issuer + '/.well-known/oauth-authorization-server')).json();
    const hostClient = await (await hostContext.request.post(discovery.registration_endpoint, {data:{redirect_uris:[redirect], client_name:'MCP first client'}})).json();
    const hostVerifier = randomBytes(48).toString('base64url');
    const hostState = randomBytes(24).toString('base64url');
    const hostAuthorization = new URL(discovery.authorization_endpoint);
    hostAuthorization.search = new URLSearchParams({response_type:'code',client_id:hostClient.client_id,redirect_uri:redirect,scope:'mcp:access',state:hostState,resource:base+'/mcp',code_challenge:createHash('sha256').update(hostVerifier).digest('base64url'),code_challenge_method:'S256'}).toString();
    await hostFirstPage.goto(hostAuthorization.href);
    await hostFirstPage.locator('input[name=username]').fill('host-first');
    await hostFirstPage.locator('input[name=password]').fill('strong-local-password');
    await hostFirstPage.getByRole('button',{name:'Create account'}).click();
    await hostFirstPage.getByRole('button',{name:'Allow',exact:true}).click();
    await hostFirstPage.waitForURL(redirect+'?**');
    await hostFirstPage.getByRole('heading',{name:'Client callback'}).waitFor();
    const hostCallback = new URL(hostFirstPage.url());
    assert.equal(hostCallback.searchParams.get('state'),hostState);
    assert.equal(hostFirstSessions.length,0);
    assert.ok(!(await hostContext.cookies()).some(cookie => cookie.name === 'game_session'));
    const hostTokenResponse = await hostContext.request.post(discovery.token_endpoint,{form:{grant_type:'authorization_code',client_id:hostClient.client_id,redirect_uri:redirect,code:hostCallback.searchParams.get('code'),code_verifier:hostVerifier,resource:base+'/mcp'}});
    assert.equal(hostTokenResponse.status(),200);
    const hostCredentials = await hostTokenResponse.json();
    const hostFirstResult = host({url:base+'/mcp',token:hostCredentials.access_token,name:'HostFirstSmoke'});
    assert.equal(hostFirstResult.tools,10);
    assert.equal(hostFirstResult.move,true);
    await hostFirstPage.goto(base);
    await gameReady(hostFirstPage);
    await hostFirstPage.mouse.click(512,440);
    await hostFirstPage.getByRole('button',{name:'Allow',exact:true}).click();
    await hostFirstPage.waitForURL(base+'/?auth=oauth');
    await gameReady(hostFirstPage);
    await hostFirstPage.mouse.click(512,440);
    await waitFor(() => joinedPlayers.length);
    assert.equal(joinedPlayers[0],hostFirstResult.player.id);
    assert.equal(hostFirstSessions[0].authMethod,'oauth');
    assert.ok(!('mcpToken' in hostFirstSessions[0]));
    assert.equal(host({url:base+'/mcp',token:hostCredentials.access_token,name:null}).player.id,joinedPlayers[0]);
    await hostFirstPage.screenshot({path:'/tmp/oauth-host-first-game.png'});
    await hostContext.close();
    const page = await context.newPage();
    const tokenSessions = capture(page);
    await page.goto(base);
    await gameReady(page);
    await page.screenshot({path:'/tmp/oauth-dual-choice.png'});
    await page.mouse.click(512,498);
    await page.waitForTimeout(300);
    await page.mouse.click(320,421);
    assert.equal(await page.evaluate(() => navigator.clipboard.readText()), base + '/mcp');
    assert.equal(tokenSessions.length, 0);
    await page.screenshot({path:'/tmp/oauth-public-url-copied-desktop.png'});
    await page.mouse.click(770,317);
    await page.mouse.click(512,384);
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
    await gameReady(oauthPage);
    await oauthPage.mouse.click(512,440);
    await oauthPage.waitForTimeout(1500);
    await oauthPage.screenshot({path:'/tmp/oauth-after-select.png'});
    await checkAuthorizationLayout(oauthPage, 'signin');
    assert.equal(await oauthPage.locator('.hint').count(), 2);

    for (const hint of await oauthPage.locator('.hint').all()) {
        assert.equal(await hint.evaluate(element => getComputedStyle(element).fontSize), '12px');
    }

    await oauthPage.locator('input[name=username]').fill('alice');
    await oauthPage.locator('input[name=password]').fill('strong-local-password');
    const loginResponse = oauthPage.waitForResponse(r => new URL(r.url()).pathname === '/oauth/login' && r.request().method() === 'POST');
    await oauthPage.getByRole('button',{name:'Create account'}).click();
    const logged = await loginResponse;
    assert.equal(logged.status(),303,'Login origin: '+logged.request().headers()['origin']);
    await oauthPage.getByRole('button', {name: 'Allow', exact: true}).waitFor();
    await checkAuthorizationLayout(oauthPage, 'consent');
    assert.equal(await oauthPage.locator('details').evaluate(element => element.open), false);
    await oauthPage.getByRole('button',{name:'Allow',exact:true}).click();
    await oauthPage.waitForURL(base+'/?auth=oauth');
    await gameReady(oauthPage);
    await oauthPage.screenshot({path:'/tmp/oauth-game-menu-before-connect.png'});
    await oauthPage.mouse.click(512,440);
    await oauthPage.screenshot({path:'/tmp/oauth-game-menu-after-connect.png'});
    const canvasLayout = await oauthPage.evaluate(() => ({
        width:innerWidth,height:innerHeight,dpr:devicePixelRatio,visibility:document.visibilityState,
        canvas:document.querySelector('canvas').getBoundingClientRect().toJSON(),
    }));
    console.log(JSON.stringify({canvasLayout}));
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
    capture(hostPage);
    const registeredResponse = await context.request.post(issuer+'/oauth/register',{data:{redirect_uris:[redirect],client_name:'Local MCP host'}});
    assert.equal(registeredResponse.status(),201);
    const registered = await registeredResponse.json();
    const authorize = new URL(issuer+'/oauth/authorize');
    authorize.search = new URLSearchParams({response_type:'code',client_id:registered.client_id,redirect_uri:redirect,scope:'openid mcp:access',state,resource:base+'/mcp',code_challenge:challenge,code_challenge_method:'S256'}).toString();
    await hostPage.goto(authorize.href);
    await hostPage.getByRole('button',{name:'Allow',exact:true}).click();
    await hostPage.waitForURL(redirect+'?**');
    await hostPage.getByRole('heading',{name:'Client callback'}).waitFor();
    const callback = new URL(hostPage.url());
    assert.equal(callback.searchParams.get('state'),state);
    assert.equal(callback.searchParams.get('iss'),issuer);
    const fields = {grant_type:'authorization_code',client_id:registered.client_id,redirect_uri:redirect,code:callback.searchParams.get('code'),code_verifier:verifier,resource:base+'/mcp'};
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
    await hostPage.goto(authorize.href);
    await hostPage.getByRole('button',{name:'Deny',exact:true}).click();
    await hostPage.waitForURL(redirect+'?**');
    await hostPage.getByRole('heading',{name:'Client callback'}).waitFor();
    const deniedCallback = new URL(hostPage.url());
    assert.equal(deniedCallback.searchParams.get('error'),'access_denied');
    assert.equal(deniedCallback.searchParams.has('code'),false);
    assert.equal(deniedCallback.searchParams.get('state'),state);
    assert.equal(deniedCallback.searchParams.get('iss'),issuer);
    const visits = await (await context.request.get(callbackOrigin+'/stats')).json();
    assert.equal(visits.selected,3);
    assert.equal(visits.unrelated,0);

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
    await gameReady(oauthPage);
    await oauthPage.mouse.click(512,384);
    await waitFor(()=>oauthSessions.length > beforeSwitch);
    const switched = oauthSessions.at(-1);
    assert.equal(switched.mcpToken,token.mcpToken);
    assert.ok(!switched.authMethod);
    const stillToken = host({url:token.mcpUrl,token:token.mcpToken,name:null});
    assert.ok(JSON.stringify(stillToken.player).includes('TokenSmoke'));
    assert.equal(failures.length,0,failures.join('\n'));
    assert.equal(unauthenticatedConsent.length,2);
    assert.equal(unauthenticatedResponses.length,2);
    assert.equal(analyticsRequests.length,0);
    assert.equal(await page.evaluate(() => 'dataLayer' in window),false);
    assert.equal(await oauthPage.evaluate(() => 'dataLayer' in window),false);
    console.log(JSON.stringify({oauthAnalyticsDisabled:true,expectedUnauthenticatedConsent:unauthenticatedConsent.length,crossOriginAllow:true,crossOriginDeny:true,hostFirst:true,publicUrlCopiedBeforeLogin:true,browserReusedPlayer:true,darkTheme:true,responsiveViewports:4,embedded:true,openid:true,inspector:!!process.env.TEST_INSPECTOR_VERSION,registration:true,refresh:true,dual:true,token:tokenResult.login,oauth:oauthResult.login,tools:oauthResult.tools,tokenMoved:tokenResult.move,oauthMoved:oauthResult.move,codeReplayRejected:true,logoutRevoked:true,switchToToken:true,tokenUnaffected:true,browserErrors:failures.length}));
} finally {
    await browser.close();
}
