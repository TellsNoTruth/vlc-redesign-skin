"""Colour sets for the two themes.

Dark values were sampled from the Figma frames (Player 247:445, Controls 491:1779,
sidebar 848:1996, Audio - Equalizer 6114:13610). The light set follows "Player - Light"
(2425:13624); that frame reads as unfinished in places, so text colours were darkened
for contrast rather than copied.
"""

DARK = dict(
    name="dark",
    chrome="#1B1B1B",       # window, top bar, control bar, rail
    panel="#0F0F0F",        # sidebar panel
    stage="#000000",        # the video area: black when there is nothing to show, as in VLC
    stage_text="#D4D4D4",   # the title under a cover, on black in both themes
    card="#1B1B1B",         # equalizer card
    card_outer="#292929",   # equalizer window body
    border="#2E2E2E",
    divider="#262626",
    text="#8F8F8F",         # time, title, labels
    text_hi="#D4D4D4",
    text_dim="#5E5E5E",
    row_text="#A3A3A3",
    row_sel="#262626",
    icon="#8F8F8F",
    icon_hover="#DADADA",
    icon_down="#707070",
    hover_bg="#2B2B2B",
    down_bg="#222222",
    close_hover="#C42B1C",
    accent="#D37918",
    accent_hover="#E58C2C",
    accent_down="#B5640F",
    on_accent="#161616",
    track="#090909",
    fill="#371F06",
    handle="#D37918",
    handle_hover="#F0A04A",
    eq_handle="#AB6314",
    toggle_off_knob="#4A4A4A",
    vol_track=None,         # None: use the Figma pixels as they are
    vol_fill_lift=0.0,
)

LIGHT = dict(
    name="light",
    chrome="#ABABAB",
    panel="#C2C1C1",
    stage="#000000",
    stage_text="#D4D4D4",
    card="#C2C1C1",
    card_outer="#B4B4B4",
    border="#979797",
    divider="#A2A2A2",
    text="#363636",
    text_hi="#141414",
    text_dim="#5C5C5C",
    row_text="#2C2C2C",
    row_sel="#ADADAD",
    icon="#3A3A3A",
    icon_hover="#0E0E0E",
    icon_down="#555555",
    hover_bg="#9D9D9D",
    down_bg="#A5A5A5",
    close_hover="#C42B1C",
    accent="#D37918",
    accent_hover="#E58C2C",
    accent_down="#B5640F",
    on_accent="#161616",
    track="#DEDEDE",
    fill="#D8BA9A",
    handle="#E8851A",
    handle_hover="#F59A38",
    eq_handle="#E8851A",
    toggle_off_knob="#8A8A8A",
    vol_track="#888888",
    vol_fill_lift=0.30,
)

THEMES = (DARK, LIGHT)
