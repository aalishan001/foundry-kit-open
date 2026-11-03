// ATS-safe resume: one column, standard headings, contacts in the body, plain bullets, real text, one font.
// Content comes only from model.json, which render.py builds from resume.json and the user's profile.
#let d = json("model.json")
#set document(title: d.title, author: d.name)
#set page(paper: "a4", margin: (x: 16mm, y: 14mm))
#set text(font: ("Arial", "Liberation Sans", "DejaVu Sans"), size: 10.5pt, hyphenate: false, lang: "en")
#set par(justify: false, leading: 0.55em, spacing: 0.7em)
#set list(marker: [•], indent: 2pt, body-indent: 6pt, spacing: 0.45em)
#show heading.where(level: 1): it => block(above: 12pt, below: 7pt, stack(spacing: 3pt,
  text(size: 11.5pt, weight: "bold", it.body),
  line(length: 100%, stroke: 0.5pt)))

#text(size: 17pt, weight: "bold", d.name)
#par(d.contact)

#for s in d.sections {
  heading(level: 1, s.heading)
  for b in s.blocks {
    if b.type == "para" { par(b.text) }
    else if b.type == "role" {
      block(above: 9pt, below: 6pt, { text(weight: "bold", b.head); if b.meta != "" { [ | ] + b.meta } })
      if b.bullets.len() > 0 { list(..b.bullets.map(x => [#x])) }
    }
    else if b.type == "bullets" { list(..b.items.map(x => [#x])) }
    else if b.type == "line" { par({ text(weight: "bold", b.label + ":"); [ ] + b.text }) }
  }
}
