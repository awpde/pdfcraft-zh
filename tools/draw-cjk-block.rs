/// Draw a text item that has CJK characters in it with a Type 3 fallback font -- the same
/// mechanism the "replace text" path uses (`text::fallback`): the glyphs come from the
/// craft-fonts document faces (the Japanese ones and any Simplified Chinese face among them), so
/// Chinese is shown instead of the '?' the standard fonts would write, and the generated font
/// carries a ToUnicode map, so the text can still be copied and searched.
///
/// The item's own standard font cannot show these characters at all, so the whole item is drawn
/// with the fallback face (its Latin glyphs come from the same face).
fn draw_cjk(doc: &mut Document, t: &AddedText, fonts: &mut Dict, out: &mut Vec<u8>) -> Result<(), EditError> {
    use crate::text::fallback::{MAX_TYPE3_GLYPHS, type3_encode, type3_font};
    let fallback = type3_font(doc, fonts, &t.text, t.family, t.bold, MAX_TYPE3_GLYPHS)?;
    let r = text_rect(t);
    let [cr, cg, cb] = t.color.map(|v| v.clamp(0.0, 1.0));
    out.extend(format!("BT {} {} {} rg\n", n(cr), n(cg), n(cb)).bytes());
    if t.char_spacing != 0.0 {
        out.extend(format!("{} Tc\n", n(t.char_spacing)).bytes());
    }
    let all = wrapped(t);
    let paragraphs: Vec<usize> = all.iter().map(|(_, _, p)| *p).collect();
    for (i, (line, ..)) in all.iter().enumerate() {
        let runs = type3_encode(&fallback, line)
            .ok_or_else(|| EditError::Invalid(format!("the text can't be shown by the {} fallback", fallback.family)))?;
        // The line's width: the advances of the characters the fallback shows.
        let w: f64 = line
            .chars()
            .filter_map(|ch| fallback.widths.iter().find(|(c, _)| *c == ch).map(|(_, adv)| *adv))
            .sum::<f64>()
            * t.size;
        // Baseline: 0.8 em below the line top, as in the standard-font path.
        let y = r[3] - (i as f64 * 1.2 + 0.95) * t.size;
        let (x, tw) = placed(t, r, &paragraphs, i, w, line.matches(' ').count(), false);
        out.extend(format!("1 0 0 1 {} {} Tm {} Tw ", n(x), n(y), n(tw)).bytes());
        for (name, bytes) in runs {
            out.extend(format!("/{name} {} Tf ", n(t.size)).bytes());
            out.extend(literal(&bytes));
            out.extend_from_slice(b" Tj\n");
        }
    }
    out.extend_from_slice(b"ET\n");
    Ok(())
}

pub(super) fn draw(doc: &mut Document, c: &Content, view: [f64; 6], taken: &Dict, existing: bool) -> Result<(Vec<u8>, Dict), EditError> {
