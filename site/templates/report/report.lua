-- Report apparatus for `spctr doc build`. Runs after citeproc.
-- Numbers sections and appendix entries, builds the contents column, turns
-- footnotes into margin notes and endnotes, expands term notes, collects asset
-- links, refuses external links outside the reference list, and assembles the
-- endmatter.

local function html(content)
  local blocks = content
  if pandoc.utils.type(content) == "Inlines" then
    blocks = { pandoc.Plain(content) }
  end
  return (pandoc.write(pandoc.Pandoc(blocks), "html", { wrap_text = "none" }):gsub("^%s+", ""):gsub("%s+$", ""))
end

local function escape(s)
  return (s:gsub("&", "&amp;"):gsub("<", "&lt;"):gsub(">", "&gt;"):gsub('"', "&quot;"))
end

local function meta_string(meta, key)
  local value = meta[key]
  if value == nil then
    error("report.md: missing metadata field '" .. key .. "'")
  end
  return pandoc.utils.stringify(value)
end

local function inline_note_html(blocks)
  local rendered = html(blocks)
  rendered = rendered:gsub("^%s*<p>", ""):gsub("</p>%s*$", "")
  rendered = rendered:gsub("</p>%s*<p>", "<br><br>")
  return rendered
end

local TERM_FIELDS = { note = true, image = true, caption = true }

-- Builds the inline filter that replaces each `[text]{term=KEY}` span with a
-- pure-CSS hover and focus note from the `terms` front matter. Every glossary
-- entry must be used, because an unused note is usually a renamed key.
local function term_expander(meta)
  local glossary = {}
  local keys = {}
  for key, entry in pairs(meta.terms or {}) do
    if pandoc.utils.type(entry) ~= "table" or entry.note == nil then
      error("report.md: term '" .. key .. "' needs a note")
    end
    for field in pairs(entry) do
      if not TERM_FIELDS[field] then
        error("report.md: term '" .. key .. "' has unknown field '" .. field .. "'")
      end
    end
    if (entry.image == nil) ~= (entry.caption == nil) then
      error("report.md: term '" .. key .. "' needs both image and caption, or neither")
    end
    local image = nil
    if entry.image ~= nil then
      image = pandoc.utils.stringify(entry.image)
      if not image:match("^assets/") then
        error("report.md: term '" .. key .. "' image must be under assets/: " .. image)
      end
      local file = io.open(image, "rb")
      if file == nil then
        error("report.md: term '" .. key .. "' image is missing: " .. image)
      end
      file:close()
    end
    glossary[key] = { note = entry.note, image = image, caption = entry.caption }
    table.insert(keys, key)
  end

  local used = {}
  local filter = { traverse = "topdown" }
  filter.Span = function(span)
    local key = span.attributes.term
    if key == nil then return nil end
    local entry = glossary[key]
    if entry == nil then
      error("report.md: unknown term '" .. key .. "' in: " .. pandoc.utils.stringify(span.content))
    end
    span.content:walk({
      Span = function(inner)
        if inner.attributes.term then
          error("report.md: term '" .. inner.attributes.term .. "' is nested inside term '" .. key .. "'")
        end
      end,
    })
    used[key] = true
    local figure = ""
    if entry.image then
      figure = string.format('<img src="%s" alt=""><span class="rk-term-caption">%s</span>',
        escape(entry.image), inline_note_html(entry.caption))
    end
    local result = pandoc.Inlines({ pandoc.RawInline("html", '<span class="rk-term" tabindex="0">') })
    result:extend(span.content)
    result:insert(pandoc.RawInline("html",
      '<span class="rk-term-note" role="tooltip">' .. figure .. inline_note_html(entry.note) .. "</span></span>"))
    return result
  end

  local function check_all_used()
    local unused = {}
    for _, key in ipairs(keys) do
      if not used[key] then table.insert(unused, key) end
    end
    if #unused > 0 then
      table.sort(unused)
      error("report.md: terms defined but never used: " .. table.concat(unused, ", "))
    end
  end
  return filter, check_all_used
end

local WIDGETS = { ["route-map"] = true, ["model-playback"] = true }
local WIDGET_ATTRIBUTES = { ["data-widget"] = true, ["data-src"] = true, ["data-defaults"] = true }

local function attribute(tag, name)
  return tag:match("%s" .. name .. '="([^"]*)"') or tag:match("%s" .. name .. "='([^']*)'")
end

local function has_flag(tag, name)
  return tag:match("%s" .. name .. "[%s>=/]") ~= nil
end

-- Checks a widget block: a fenced Div carrying data-widget, data-src and
-- data-defaults whose content is the static figure the widget hydrates. Its
-- controls are native elements with ids inside one form, and each named
-- control starts in the state data-defaults declares, so the static figure
-- shows that state.
local function check_widget(div)
  local name = div.attributes["data-widget"]
  local where = "report.md: widget '" .. (div.identifier ~= "" and div.identifier or name) .. "'"
  if not WIDGETS[name] then
    error(where .. ": unknown widget '" .. name .. "'")
  end
  if div.identifier == "" then
    error("report.md: " .. name .. " widget needs an id")
  end
  for key in pairs(div.attributes) do
    if not WIDGET_ATTRIBUTES[key] then
      error(where .. ": unknown attribute '" .. key .. "'")
    end
  end
  local src = div.attributes["data-src"]
  if src == nil or not src:match("^assets/[%w_%-/%.]+%.json$") or src:match("%.%.") then
    error(where .. ": data-src must name a .json file under assets/")
  end
  local file = io.open(src, "rb")
  if file == nil then
    error(where .. ": data file is missing: " .. src)
  end
  file:close()
  local ok, defaults = pcall(pandoc.json.decode, div.attributes["data-defaults"] or "", false)
  if not ok or type(defaults) ~= "table" or defaults[1] ~= nil then
    error(where .. ": data-defaults must be a JSON object")
  end
  if #div.content == 0 then
    error(where .. " needs its static figure inside")
  end
  local markup = html(div.content)
  local forms = select(2, markup:gsub("<form[%s>]", ""))
  local controls = {}
  for tag, kind in markup:gmatch("(<(%a+)[^>]*>)") do
    if kind == "input" or kind == "select" or kind == "button" or kind == "textarea" then
      if attribute(tag, "id") == nil then
        error(where .. ": every control needs an id: " .. tag)
      end
      local control = attribute(tag, "name")
      if control then
        controls[control] = controls[control] or {}
        table.insert(controls[control], tag)
      end
    end
  end
  if next(controls) ~= nil and forms ~= 1 then
    error(where .. ": named controls belong in exactly one form")
  end
  for control in pairs(controls) do
    if defaults[control] == nil then
      error(where .. ": control '" .. control .. "' has no default")
    end
  end
  for key, value in pairs(defaults) do
    local tags = controls[key]
    if tags == nil then
      error(where .. ": default '" .. key .. "' has no control named " .. key)
    end
    local kind = attribute(tags[1], "type") or tags[1]:match("^<(%a+)")
    local state
    if kind == "radio" then
      for _, tag in ipairs(tags) do
        if has_flag(tag, "checked") then state = attribute(tag, "value") end
      end
    elseif kind == "checkbox" then
      state = has_flag(tags[1], "checked")
    elseif kind == "range" then
      state = tonumber(attribute(tags[1], "value") or "")
    else
      error(where .. ": control '" .. key .. "' must be a radio group, checkbox or range")
    end
    if state ~= value then
      error(where .. ": control '" .. key .. "' starts at " .. tostring(state) ..
        ", but data-defaults says " .. tostring(value))
    end
  end
  div.classes:insert(1, "rk-widget")
end

local HERO_MEDIA = { png = "img", jpg = "img", jpeg = "img", webp = "img", svg = "img", mp4 = "video", webm = "video" }

-- Renders the `hero` front matter (an assets/ image or looping video and its
-- caption) as the figure between the subtitle and the byline. On explorer
-- pages `hero: {widget: ID}` instead moves the widget block with that id out
-- of the body into the hero.
local function hero_html(meta, body, explorer)
  local hero = meta.hero
  if hero == nil then return nil end
  if pandoc.utils.type(hero) == "table" and hero.widget ~= nil then
    for field in pairs(hero) do
      if field ~= "widget" then
        error("report.md: a widget hero takes no '" .. field .. "'; the widget block carries its own caption")
      end
    end
    local id = pandoc.utils.stringify(hero.widget)
    if not explorer then
      error("report.md: hero widget '" .. id .. "' needs layout: explorer")
    end
    for i, block in ipairs(body) do
      if block.t == "Div" and block.identifier == id then
        if block.attributes["data-widget"] == nil then
          error("report.md: hero widget '" .. id .. "' is not a widget block")
        end
        body:remove(i)
        return '<div class="rk-hero-widget">' .. html({ block }) .. "</div>"
      end
    end
    error("report.md: hero widget '" .. id .. "' is not a top-level block of the body")
  end
  if pandoc.utils.type(hero) ~= "table" or hero.image == nil or hero.caption == nil then
    error("report.md: hero needs image and caption")
  end
  for field in pairs(hero) do
    if field ~= "image" and field ~= "caption" then
      error("report.md: hero has unknown field '" .. field .. "'")
    end
  end
  local image = pandoc.utils.stringify(hero.image)
  if not image:match("^assets/") then
    error("report.md: hero image must be under assets/: " .. image)
  end
  local file = io.open(image, "rb")
  if file == nil then
    error("report.md: hero image is missing: " .. image)
  end
  file:close()
  local kind = HERO_MEDIA[(image:match("%.(%w+)$") or ""):lower()]
  if kind == nil then
    error("report.md: hero image must be png, jpg, webp, svg, mp4 or webm: " .. image)
  end
  local media
  if kind == "video" then
    media = string.format('<video src="%s" autoplay muted loop playsinline></video>', escape(image))
  else
    media = string.format('<img src="%s" alt="">', escape(image))
  end
  return string.format('<figure class="rk-hero-figure">%s<figcaption>%s</figcaption></figure>',
    media, inline_note_html(hero.caption))
end

-- Collects each reference-list entry as inline HTML keyed by citation id, so a
-- citation can carry its full entry as a hover and focus preview.
local function reference_entries(refs_div)
  local entries = {}
  if refs_div == nil then return entries end
  for _, entry in ipairs(refs_div.content) do
    local id = entry.identifier:match("^ref%-(.+)$")
    if entry.t ~= "Div" or id == nil then
      error("report.md: unexpected reference list entry from citeproc")
    end
    local label, text = nil, nil
    local para = entry.content[1]
    if #entry.content == 1 and para.t == "Para" then
      for _, part in ipairs(para.content) do
        if part.t == "Span" and part.classes:includes("csl-left-margin") then
          label = pandoc.utils.stringify(part):gsub("%s+$", "")
        elseif part.t == "Span" and part.classes:includes("csl-right-inline") then
          text = html(part.content)
        end
      end
    end
    if label == nil or text == nil then
      error("report.md: reference '" .. id .. "' lacks the numbered CSL layout")
    end
    entries[id] = string.format('<span class="rk-pop-entry"><span class="rk-num">%s</span>%s</span>', escape(label), text)
  end
  return entries
end

local function is_review_link(target, review_hosts)
  local host = target:match("^https?://([^/#?]+)")
  return host ~= nil and review_hosts[host] == true
end

local KINDS = { report = true, proposal = true, synthesis = true }

function Pandoc(doc)
  local meta = doc.meta
  -- spctr has already refused any layout but essay and explorer.
  local explorer = meta.layout ~= nil and pandoc.utils.stringify(meta.layout) == "explorer"
  for _, key in ipairs({ "title", "kicker", "authors", "document_id", "revision", "year", "url", "abstract" }) do
    meta_string(meta, key)
  end
  if not explorer then
    meta_string(meta, "subtitle")
  end
  local kind = meta_string(meta, "kind")
  if not KINDS[kind] then
    error("report.md: kind must be report, proposal or synthesis, found '" .. kind .. "'")
  end

  local refs_div = nil
  local body = pandoc.Blocks({})
  for _, block in ipairs(doc.blocks) do
    if block.t == "Div" and block.identifier == "refs" then
      refs_div = block
    else
      body:insert(block)
    end
  end

  local review_hosts = {}
  for _, host in ipairs(meta["rk-review-host"] or {}) do
    review_hosts[pandoc.utils.stringify(host)] = true
  end

  for _, block in ipairs(body) do
    if block.t == "Header" then
      block.content:walk({
        Span = function(span)
          if span.attributes.term then
            error("report.md: terms are not allowed in headings: " .. pandoc.utils.stringify(block.content))
          end
        end,
      })
    end
  end
  local hero_widget = meta.hero ~= nil and pandoc.utils.type(meta.hero) == "table" and meta.hero.widget ~= nil
    and pandoc.utils.stringify(meta.hero.widget) or nil
  local widget_chapters = {}
  local chapter = nil
  for i, block in ipairs(body) do
    if block.t == "Header" and block.level == 1 then
      chapter = block.identifier
    end
    body[i] = pandoc.Blocks({ block }):walk({
      Div = function(div)
        if div.attributes["data-widget"] ~= nil then
          if not explorer then
            error("report.md: widget blocks need layout: explorer")
          end
          check_widget(div)
          if chapter and div.identifier ~= hero_widget then widget_chapters[chapter] = true end
          return div
        end
      end,
      RawBlock = function(raw)
        if raw.format == "html" and raw.text:match("data%-widget") then
          error("report.md: declare widgets as fenced divs, not raw HTML: " .. raw.text:sub(1, 80))
        end
      end,
    })[1]
  end

  local expand_terms, check_all_used = term_expander(meta)
  body = body:walk(expand_terms)
  meta.abstract = pandoc.MetaBlocks(pandoc.Blocks(meta.abstract):walk(expand_terms))
  check_all_used()

  local cited_urls = {}
  if refs_div then
    refs_div:walk({
      Link = function(link) cited_urls[link.target] = true end,
    })
  end
  local function is_allowed(target)
    return is_review_link(target, review_hosts) or cited_urls[target] == true
  end

  local external = {}
  local assets = {}
  local seen_assets = {}
  local function note_asset(target, text)
    if not seen_assets[target] then
      seen_assets[target] = true
      table.insert(assets, { target = target, text = text })
    end
  end
  local function scan_raw(text)
    for href in text:gmatch('href="(https?://[^"]+)"') do
      if not is_allowed(href) then table.insert(external, href) end
    end
    for href, label in text:gmatch('<a[^>]-href="(assets/[^"#]+)"[^>]*>(.-)</a>') do
      note_asset(href, (label:gsub("<[^>]+>", "")))
    end
  end

  local notes = {}
  body = body:walk({
    Link = function(link)
      if link.target:match("^https?://") then
        if not is_allowed(link.target) then table.insert(external, link.target) end
      elseif link.target:match("^assets/") then
        note_asset((link.target:gsub("#.*$", "")), pandoc.utils.stringify(link.content))
      end
    end,
    RawBlock = function(raw)
      if raw.format == "html" then scan_raw(raw.text) end
    end,
    RawInline = function(raw)
      if raw.format == "html" then scan_raw(raw.text) end
    end,
  })
  if #external > 0 then
    error("report.md: external links in the body must be cited as references:\n  " .. table.concat(external, "\n  "))
  end

  local entries = reference_entries(refs_div)
  local expand_cites = {
    Cite = function(cite)
      local previews = {}
      for _, citation in ipairs(cite.citations) do
        local entry = entries[citation.id]
        if entry == nil then
          error("report.md: citation '" .. citation.id .. "' has no reference list entry")
        end
        table.insert(previews, entry)
      end
      return {
        pandoc.RawInline("html", '<span class="rk-cite">'),
        cite,
        pandoc.RawInline("html", '<span class="rk-pop" role="tooltip">' .. table.concat(previews) .. "</span></span>"),
      }
    end,
  }
  body = body:walk(expand_cites)
  meta.abstract = pandoc.MetaBlocks(pandoc.Blocks(meta.abstract):walk(expand_cites))

  local hero = hero_html(meta, body, explorer)

  body = body:walk({
    Note = function(note)
      table.insert(notes, note.content)
      local n = #notes
      local text = inline_note_html(note.content)
      return pandoc.RawInline("html",
        string.format('<sup class="rk-noteref" id="noteref-%d"><a href="#note-%d">%d</a>' ..
          '<span class="rk-pop" role="tooltip"><span class="rk-num">%d</span> %s</span></sup>' ..
          '<span class="rk-sidenote" aria-hidden="true"><span class="rk-sidenote-body"><span class="rk-sidenote-num">%d</span> %s</span></span>',
          n, n, n, n, text, n, text))
    end,
  })

  local toc = {}
  local section, sub, appendix_count = 0, 0, 0
  local in_appendix = false
  local current = nil
  local tracked = 0
  -- Each top-level entry's section gets a numbered class, which names the view
  -- timeline that marks it as the reader's current section.
  local function track(h, entry)
    tracked = tracked + 1
    entry.track = tracked
    h.classes:insert("rk-s" .. tracked)
  end
  body = body:walk({
    Header = function(h)
      if h.classes:includes("appendix") then
        if h.level ~= 1 then
          error("report.md: the {.appendix} heading must be a level-1 heading")
        end
        in_appendix = true
        h.classes = pandoc.List({ "rk-appendix-head" })
        h.level = 2
        return h
      end
      local label
      if in_appendix then
        if h.level == 1 then
          error("report.md: level-1 heading after the appendix: " .. pandoc.utils.stringify(h.content))
        end
        if h.level == 2 then
          appendix_count = appendix_count + 1
          label = "A." .. appendix_count
          local entry = { id = h.identifier, num = label, title = h.content:clone(), appendix = true }
          table.insert(toc, entry)
          track(h, entry)
        end
      elseif h.level == 1 then
        section = section + 1
        sub = 0
        label = tostring(section)
        current = { id = h.identifier, num = label, title = h.content:clone(), children = {} }
        table.insert(toc, current)
        track(h, current)
      elseif h.level == 2 then
        if current == nil then
          error("report.md: level-2 heading before the first section: " .. pandoc.utils.stringify(h.content))
        end
        sub = sub + 1
        label = section .. "." .. sub
        table.insert(current.children, { id = h.identifier, num = label, title = h.content:clone() })
      end
      if label then
        h.content:insert(1, pandoc.RawInline("html", '<span class="rk-num">' .. label .. "</span>"))
      end
      -- Shifted down one level because the title is the page's only h1.
      h.level = h.level + 1
      return h
    end,
    -- Wide tables scroll inside their own box so that narrow screens keep the
    -- page itself from scrolling sideways.
    Table = function(t)
      return pandoc.Div({ t }, pandoc.Attr("", { "table-wrap" }))
    end,
  })

  local function toc_item(entry)
    local class = entry.track and string.format(' class="rk-t%d"', entry.track) or ""
    local s = string.format('<li><a href="#%s"%s><span class="rk-num">%s</span><span>%s</span></a>',
      entry.id, class, entry.num, html(entry.title))
    if entry.children and #entry.children > 0 then
      local kids = {}
      for _, c in ipairs(entry.children) do table.insert(kids, toc_item(c)) end
      s = s .. "<ul>" .. table.concat(kids) .. "</ul>"
    end
    return s .. "</li>"
  end
  local main_items, app_items = {}, {}
  for _, e in ipairs(toc) do
    table.insert(e.appendix and app_items or main_items, toc_item(e))
  end

  local has_refs = refs_div ~= nil and #refs_div.content > 0
  local end_items = { '<li><a href="#cite-this">Cite this ' .. kind .. '</a></li>' }
  if has_refs then table.insert(end_items, '<li><a href="#references">References</a></li>') end
  if #notes > 0 then table.insert(end_items, '<li><a href="#notes">Notes</a></li>') end
  if #assets > 0 then table.insert(end_items, '<li><a href="#data">Data and receipts</a></li>') end

  local toc_html = '<nav class="rk-toc" aria-label="Contents"><p class="rk-toc-head">Contents</p><ul>' ..
    table.concat(main_items) .. "</ul>"
  if #app_items > 0 then
    toc_html = toc_html .. '<p class="rk-toc-head">Appendix</p><ul>' .. table.concat(app_items) .. "</ul>"
  end
  toc_html = toc_html .. '<ul class="rk-toc-end">' .. table.concat(end_items) .. "</ul></nav>"

  local labels, names, rules = {}, { "--rk-toc" }, {}
  for _, e in ipairs(toc) do
    table.insert(labels, string.format('<span class="rk-t%d"><span class="rk-num">%s</span>%s</span>',
      e.track, e.num, html(e.title)))
    table.insert(names, "--rk-s" .. e.track)
    table.insert(rules, string.format("section.rk-s%d{view-timeline-name:--rk-s%d}.rk-t%d{animation-timeline:--rk-s%d}",
      e.track, e.track, e.track, e.track))
  end
  local tocbar_html = '<div class="rk-tocbar"><details><summary><span class="rk-tocbar-head">Contents</span>' ..
    '<span class="rk-tocbar-current">' .. table.concat(labels) .. "</span></summary><ul>" ..
    table.concat(main_items) .. table.concat(app_items) .. "</ul></details></div>"
  local timeline_css = ".rk-layout{timeline-scope:" .. table.concat(names, ",") .. "}" .. table.concat(rules)

  local title = meta_string(meta, "title")
  local authors = meta_string(meta, "authors")
  local year = meta_string(meta, "year")
  local revision = meta_string(meta, "revision")
  local url = meta_string(meta, "url")
  local document_id = meta_string(meta, "document_id")

  local bibtex = string.format(
    "@techreport{specter-%s-%s,\n  title = {%s},\n  author = {%s},\n  institution = {Specter Labs},\n  year = {%s},\n  note = {Revision %s},\n  url = {%s}\n}",
    document_id, revision, title, authors, year, revision, url)
  local parts = {
    '<footer class="rk-endmatter">',
    '<section id="cite-this"><h2>Cite this ' .. kind .. '</h2><p>' ..
      string.format("%s. %s. <em>%s</em>. Specter Labs %s, revision %s. %s",
        escape(authors), escape(year), escape(title), kind, escape(revision), escape(url)) ..
      "</p><pre>" .. escape(bibtex) .. "</pre></section>",
  }
  if has_refs then
    table.insert(parts, '<section id="references"><h2>References</h2>' .. html(refs_div.content) .. "</section>")
  end
  if #notes > 0 then
    local items = {}
    for i, content in ipairs(notes) do
      table.insert(items, string.format('<li id="note-%d">%s <a class="rk-back" href="#noteref-%d" aria-label="Back to text">&#8617;&#xFE0E;</a></li>',
        i, inline_note_html(content), i))
    end
    table.insert(parts, '<section id="notes"><h2>Notes</h2><ol class="rk-notes">' .. table.concat(items) .. "</ol></section>")
  end
  if #assets > 0 then
    local items = {}
    for _, a in ipairs(assets) do
      table.insert(items, string.format('<li><a href="%s">%s</a> <span class="rk-path">%s</span></li>',
        escape(a.target), escape(a.text), escape(a.target:gsub("^assets/", ""))))
    end
    table.insert(parts, '<section id="data"><h2>Data and receipts</h2><ul class="rk-data">' .. table.concat(items) .. "</ul></section>")
  end
  table.insert(parts, "</footer>")

  local word_count = select(2, pandoc.utils.stringify(pandoc.Pandoc(body)):gsub("%S+", ""))
    + select(2, pandoc.utils.stringify(meta.abstract):gsub("%S+", ""))
  local minutes = math.max(1, math.floor(word_count / 230 + 0.5))

  if explorer then
    local cards = {}
    for _, e in ipairs(toc) do
      if not e.appendix then
        table.insert(cards, string.format('<li><a href="#%s"><span class="rk-num">%s</span>' ..
          '<span class="rk-hub-title">%s</span>%s</a></li>', e.id, e.num, html(e.title),
          widget_chapters[e.id] and '<span class="rk-hub-tag">Interactive</span>' or ""))
      end
    end
    meta["rk-hub"] = pandoc.RawInline("html",
      '<nav class="rk-hub" aria-label="Chapters"><ol>' .. table.concat(cards) .. "</ol></nav>")
    meta["rk-layout"] = "explorer"
  else
    meta["rk-toc"] = pandoc.RawInline("html", toc_html)
  end
  meta["rk-kind"] = kind:sub(1, 1):upper() .. kind:sub(2)
  meta["rk-tocbar"] = pandoc.RawInline("html", tocbar_html)
  meta["rk-timelines"] = pandoc.RawInline("html", timeline_css)
  if hero then meta["rk-hero"] = pandoc.RawInline("html", hero) end
  meta["rk-endmatter"] = pandoc.RawInline("html", table.concat(parts))
  meta["rk-minutes"] = tostring(minutes)
  meta["pagetitle"] = title .. " | Specter Labs"
  doc.blocks = body
  return doc
end
