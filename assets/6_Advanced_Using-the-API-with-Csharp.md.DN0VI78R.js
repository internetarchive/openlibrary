import{_ as e,c as p,o as t,j as s,ag as l,a as n}from"./chunks/framework.BRQrZDXk.js";const q=JSON.parse('{"title":"","description":"","frontmatter":{},"headers":[],"relativePath":"6_Advanced/Using-the-API-with-Csharp.md","filePath":"6_Advanced/Using-the-API-with-Csharp.md"}'),i={name:"6_Advanced/Using-the-API-with-Csharp.md"};function o(r,a,c,u,g,d){return t(),p("div",null,a[0]||(a[0]=[s("p",null,"``# C# API examples",-1),s("h2",{id:"note-on-openlibrary-people-api-s",tabindex:"-1"},[n("Note: on OpenLibrary people API's "),s("a",{class:"header-anchor",href:"#note-on-openlibrary-people-api-s","aria-label":`Permalink to "Note: on OpenLibrary people API's"`},"​")],-1),s("p",null,"For API's that reference a specific users data such as those API's that start with people. Substitute {Profile Display Name} with the authenticated user or public data's profile display name.",-1),s("p",null,[s("a",{href:"https://openlibrary.org/people/",Profile:"",Display:"",Name:"",target:"_blank",rel:"noreferrer"},"https://openlibrary.org/people/"),n("/books/want-to-read.json "),s("a",{href:"https://openlibrary.org/people/",Profile:"",Display:"",Name:"",target:"_blank",rel:"noreferrer"},"https://openlibrary.org/people/"),n("/books/currently-reading.json "),s("a",{href:"https://openlibrary.org/people/",Profile:"",Display:"",Name:"",target:"_blank",rel:"noreferrer"},"https://openlibrary.org/people/"),n("/books/already-read.json")],-1),l(`<h2 id="login-into-openlibrary-with-access-credentials" tabindex="-1">Login into OpenLibrary with Access Credentials <a class="header-anchor" href="#login-into-openlibrary-with-access-credentials" aria-label="Permalink to &quot;Login into OpenLibrary with Access Credentials&quot;">​</a></h2><div class="language- vp-adaptive-theme"><button title="Copy Code" class="copy"></button><span class="lang"></span><pre class="shiki shiki-themes github-light github-dark vp-code" tabindex="0"><code><span class="line"><span></span></span>
<span class="line"><span>public async Task&lt;ErrorReturn&gt; Login(string AccessKeyString, string SecretString, string OL_ProfileID)</span></span>
<span class="line"><span>{</span></span>
<span class="line"><span>    _AccessKeyString = AccessKeyString;</span></span>
<span class="line"><span>    _SecretString = SecretString;   </span></span>
<span class="line"><span>    _OL_ProfileID = OL_ProfileID;</span></span>
<span class="line"><span></span></span>
<span class="line"><span>    ErrorReturn loginReturn = new ErrorReturn();</span></span>
<span class="line"><span>    try</span></span>
<span class="line"><span>    {</span></span>
<span class="line"><span>       </span></span>
<span class="line"><span>        var client = new HttpClient();</span></span>
<span class="line"><span>       </span></span>
<span class="line"><span>        var content = new StringContent($&quot;{{\\&quot;access\\&quot;: \\&quot;{AccessKeyString}\\&quot;, \\&quot;secret\\&quot;: \\&quot;{SecretString}\\&quot;}}&quot;, Encoding.Unicode, &quot;application/json&quot;);</span></span>
<span class="line"><span>        client.DefaultRequestHeaders.Add(&quot;Accept&quot;, &quot;application/json&quot;);</span></span>
<span class="line"><span>        client.DefaultRequestHeaders.Add(&quot;User-Agent&quot;, &quot;MyNextBook&quot;);</span></span>
<span class="line"><span>       </span></span>
<span class="line"><span>        var response = await client.PostAsync(LoginUrl, content);</span></span>
<span class="line"><span></span></span>
<span class="line"><span>        if (response.IsSuccessStatusCode)</span></span>
<span class="line"><span>        {</span></span>
<span class="line"><span>       </span></span>
<span class="line"><span></span></span>
<span class="line"><span>            var sessionCookie = response.Headers.GetValues(&quot;Set-Cookie&quot;);</span></span>
<span class="line"><span>            ol_sessionid = string.Join(&quot;, &quot;, sessionCookie);</span></span>
<span class="line"><span>            var ss = ol_sessionid.Split(&quot;;&quot;);</span></span>
<span class="line"><span>            string s = ss[0];</span></span>
<span class="line"><span>            ol_sessionid = s;</span></span>
<span class="line"><span>            //return string.Join(&quot;, &quot;, sessionCookie);</span></span>
<span class="line"><span>            loginReturn.success = true;</span></span>
<span class="line"><span>            return loginReturn;</span></span>
<span class="line"><span>        }</span></span>
<span class="line"><span>        else</span></span>
<span class="line"><span>        {</span></span>
<span class="line"><span>            loginReturn.ErrorCode = &quot;GEN-001&quot;;</span></span>
<span class="line"><span>            ol_sessionid = &quot;&quot;;</span></span>
<span class="line"><span>            Debug.WriteLine($&quot;Login failed with status code: {response.StatusCode}&quot;);</span></span>
<span class="line"><span>            loginReturn.ErrorMessage = response.Content.ReadAsStringAsync().Result;</span></span>
<span class="line"><span>            loginReturn.Success = false;</span></span>
<span class="line"><span>            loginReturn.ErrorReason = response.ReasonPhrase;</span></span>
<span class="line"><span>            return loginReturn;</span></span>
<span class="line"><span>        }</span></span>
<span class="line"><span>    }</span></span>
<span class="line"><span>    catch (Exception ex)</span></span>
<span class="line"><span>    {</span></span>
<span class="line"><span></span></span>
<span class="line"><span>        Debug.WriteLine($&quot;Exception occurred during login: {ex.Message} : {ex.ToString()}&quot;);</span></span>
<span class="line"><span>        loginReturn.ErrorCode = &quot;GEN-002&quot;;</span></span>
<span class="line"><span>        loginReturn.ErrorMessage = ex.Message;</span></span>
<span class="line"><span>        loginReturn.Success = false;</span></span>
<span class="line"><span>        loginReturn.ErrorReason = ex.ToString();</span></span>
<span class="line"><span>        return loginReturn;</span></span>
<span class="line"><span>    }</span></span>
<span class="line"><span>}</span></span></code></pre></div>`,2)]))}const _=e(i,[["render",o]]);export{q as __pageData,_ as default};
