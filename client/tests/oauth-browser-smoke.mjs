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
    await oauthPage.waitForTimeout(5000);
    await oauthPage.mouse.click(512,440);
    await oauthPage.waitForTimeout(1500);
    await oauthPage.screenshot({path:'/tmp/oauth-after-select.png'});
    await oauthPage.getByRole('button',{name:'Approve local test'}).click();
    await oauthPage.waitForURL(base+'/?auth=oauth');
    await oauthPage.waitForTimeout(5000);
    await oauthPage.mouse.click(512,440);
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
    const authorize = new URL(issuer+'/authorize');
    authorize.search = new URLSearchParams({response_type:'code',client_id:'host',redirect_uri:issuer+'/host-callback',scope:'mcp:access',state,resource:base+'/mcp',code_challenge:challenge,code_challenge_method:'S256'}).toString();
    await hostPage.goto(authorize.href);
    await hostPage.getByRole('button',{name:'Approve local test'}).click();
    await hostPage.waitForURL(issuer+'/host-callback?**');
    const callback = new URL(hostPage.url());
    assert.equal(callback.searchParams.get('state'),state);
    assert.equal(callback.searchParams.get('iss'),issuer);
    const fields = {grant_type:'authorization_code',client_id:'host',redirect_uri:issuer+'/host-callback',code:callback.searchParams.get('code'),code_verifier:verifier,resource:base+'/mcp'};
    const response = await fetch(issuer+'/token',{method:'POST',body:new URLSearchParams(fields)});
    assert.equal(response.status,200);
    const credentials = await response.json();
    const replay = await fetch(issuer+'/token',{method:'POST',body:new URLSearchParams(fields)});
    assert.equal(replay.status,400);
    const oauthResult = host({url:oauth.mcpUrl,token:credentials.access_token,name:'OAuthSmoke'});
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
    assert.equal(denied.status(),404);
    const beforeSwitch = oauthSessions.length;
    await oauthPage.mouse.click(512,384);
    await waitFor(()=>oauthSessions.length > beforeSwitch);
    const switched = oauthSessions.at(-1);
    assert.equal(switched.mcpToken,token.mcpToken);
    assert.ok(!switched.authMethod);
    const stillToken = host({url:token.mcpUrl,token:token.mcpToken,name:null});
    assert.ok(JSON.stringify(stillToken.player).includes('TokenSmoke'));
    assert.equal(failures.length,0,failures.join('\n'));
    console.log(JSON.stringify({dual:true,token:tokenResult.login,oauth:oauthResult.login,tools:oauthResult.tools,tokenMoved:tokenResult.move,oauthMoved:oauthResult.move,codeReplayRejected:true,logoutRevoked:true,switchToToken:true,tokenUnaffected:true,browserErrors:failures.length}));
} finally {
    await browser.close();
}
