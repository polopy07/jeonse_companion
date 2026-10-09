/*
 * 목업 미리보기용 최소 런타임.
 * screens/*.dc.html 을 브라우저에서 바로 열면 {{값}}, <sc-if>, <sc-for>, onClick 을 처리해 화면을 그린다.
 * 실제 앱 코드가 아니며, 프론트 구현은 React로 새로 작성한다.
 */
(function () {
  class DCLogic {
    constructor(props) {
      this.props = props || {};
      this.state = {};
    }
    setState(patch) {
      Object.assign(this.state, typeof patch === 'function' ? patch(this.state) : patch);
      if (this.__render) this.__render();
    }
    forceUpdate() {
      if (this.__render) this.__render();
    }
  }
  window.DCLogic = DCLogic;

  var WHOLE = /^\s*\{\{([^}]+)\}\}\s*$/;
  var ANY = /\{\{([^}]+)\}\}/g;

  function lookup(scope, path) {
    path = path.trim();
    if (path === 'true') return true;
    if (path === 'false') return false;
    if (/^-?\d+(\.\d+)?$/.test(path)) return Number(path);
    return path.split('.').reduce(function (o, k) { return o == null ? undefined : o[k]; }, scope);
  }

  function interp(str, scope) {
    return str.replace(ANY, function (_, p) {
      var v = lookup(scope, p);
      return v == null ? '' : String(v);
    });
  }

  function renderChildren(node, scope, out) {
    node.childNodes.forEach(function (c) { renderNode(c, scope, out); });
  }

  function renderNode(n, scope, out) {
    if (n.nodeType === 3) {
      out.appendChild(document.createTextNode(interp(n.nodeValue, scope)));
      return;
    }
    if (n.nodeType !== 1) return;
    var tag = n.localName;
    if (tag === 'sc-if') {
      var m = (n.getAttribute('value') || '').match(WHOLE);
      if (m && lookup(scope, m[1])) renderChildren(n, scope, out);
      return;
    }
    if (tag === 'sc-for') {
      var lm = (n.getAttribute('list') || '').match(WHOLE);
      var list = (lm && lookup(scope, lm[1])) || [];
      var as = n.getAttribute('as') || 'item';
      list.forEach(function (it, i) {
        var s = Object.create(scope);
        s[as] = it;
        s.$index = i;
        renderChildren(n, s, out);
      });
      return;
    }
    var el = document.createElementNS(n.namespaceURI, n.localName);
    Array.prototype.forEach.call(n.attributes, function (a) {
      var name = a.name;
      if (/^hint-/.test(name)) return;
      if (/^on/.test(name)) {
        var hm = a.value.match(WHOLE);
        var fn = hm && lookup(scope, hm[1]);
        if (typeof fn === 'function') el.addEventListener(name.slice(2).toLowerCase(), fn);
        return;
      }
      el.setAttribute(name, interp(a.value, scope));
    });
    renderChildren(n, scope, el);
    out.appendChild(el);
  }

  function boot() {
    var root = document.querySelector('x-dc');
    var script = document.querySelector('script[data-dc-script]');
    if (!root) return;

    var helmet = root.querySelector('helmet');
    if (helmet) {
      Array.prototype.slice.call(helmet.children).forEach(function (c) { document.head.appendChild(c); });
      helmet.remove();
    }

    var tpl = document.createElement('div');
    while (root.firstChild) tpl.appendChild(root.firstChild);

    var props = {};
    if (script) {
      try {
        var decl = JSON.parse(script.getAttribute('data-props') || '{}');
        Object.keys(decl).forEach(function (k) {
          if (k.charAt(0) !== '$' && decl[k] && 'default' in decl[k]) props[k] = decl[k]['default'];
        });
      } catch (e) { /* 선언이 없으면 기본값 없이 그림 */ }
    }

    var Comp = script
      ? new Function('DCLogic', script.textContent + '\n;return Component;')(DCLogic)
      : DCLogic;
    var inst = new Comp(props);
    inst.__render = function () {
      var frag = document.createDocumentFragment();
      renderChildren(tpl, inst.renderVals ? inst.renderVals() : {}, frag);
      root.replaceChildren(frag);
    };

    root.style.display = 'block';
    var embedded = window.self !== window.top;
    if (!embedded) {
      document.body.style.background = '#D9D6CF';
      root.style.width = 'fit-content';
      root.style.margin = '24px auto';
      root.style.borderRadius = '28px';
      root.style.overflow = 'hidden';
      root.style.boxShadow = '0 8px 32px rgba(0,0,0,0.18)';
    }
    inst.__render();
    if (inst.componentDidMount) inst.componentDidMount();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
