// Создано из public/mascot/*.svg: фирменные цвета заменены переменными темы (--p-body и др., globals.css).
// Перегенерировать при замене рисунков: цвета #3B6FC4 #2B58A5 #7FA9EE #5B8FE0 #1B3A73 → var(--p-…).

export const PENGUIN_POSES = {
  "standing": `<defs>
<clipPath id="bodyClip"><path d="M200 40 C262 40 304 86 304 148 C304 190 326 232 336 292 C346 360 322 440 262 456 C235 463 165 463 138 456 C78 440 54 360 64 292 C74 232 96 190 96 148 C96 86 138 40 200 40 Z"/></clipPath>
<clipPath id="bellyClip"><path d="M200 196 C252 196 286 246 292 306 C298 372 278 428 236 442 C220 447 180 447 164 442 C122 428 102 372 108 306 C114 246 148 196 200 196 Z"/></clipPath>
</defs>
<g>
<ellipse cx="200" cy="476" rx="128" ry="14" fill="var(--p-ink)" opacity="0.16"/>
</g>
<g>
<g transform="translate(146 468)">
<path d="M-40 10 C-44 -4 -30 -14 -12 -14 C6 -16 30 -10 40 2 C46 12 40 18 30 18 L-30 18 C-38 18 -41 14 -40 10 Z" fill="#B8693A"/>
<path d="M-24 -6 L-28 12 M-6 -10 L-8 14 M12 -8 L12 14" stroke="#8A4A26" stroke-width="3" stroke-linecap="round" fill="none"/>
</g>
<g transform="translate(254 468) scale(-1 1)">
<path d="M-40 10 C-44 -4 -30 -14 -12 -14 C6 -16 30 -10 40 2 C46 12 40 18 30 18 L-30 18 C-38 18 -41 14 -40 10 Z" fill="#B8693A"/>
<path d="M-24 -6 L-28 12 M-6 -10 L-8 14 M12 -8 L12 14" stroke="#8A4A26" stroke-width="3" stroke-linecap="round" fill="none"/>
</g>
</g>
<g>
<path d="M200 40 C262 40 304 86 304 148 C304 190 326 232 336 292 C346 360 322 440 262 456 C235 463 165 463 138 456 C78 440 54 360 64 292 C74 232 96 190 96 148 C96 86 138 40 200 40 Z" fill="var(--p-body)"/>
<g clip-path="url(#bodyClip)">
<path d="M262 42 C286 68 290 120 282 160 C278 202 306 240 308 296 C312 360 296 424 254 450 L420 480 L420 0 L262 0 Z" fill="var(--p-dark)" opacity="0.55"/>
<ellipse cx="148" cy="74" rx="34" ry="12" transform="rotate(-28 148 74)" fill="var(--p-light)" opacity="0.55"/>
</g>
<path d="M200 196 C252 196 286 246 292 306 C298 372 278 428 236 442 C220 447 180 447 164 442 C122 428 102 372 108 306 C114 246 148 196 200 196 Z" fill="#F8E7BE"/>
<g clip-path="url(#bellyClip)">
<ellipse cx="190" cy="476" rx="130" ry="56" fill="#E9CF98" opacity="0.6"/>
</g>
<g stroke="#E3C98C" stroke-width="3.5" stroke-linecap="round" fill="none">
<path d="M186 250 Q193 260 200 248"/>
<path d="M204 262 Q211 272 218 260"/>
<path d="M172 270 Q179 280 186 268"/>
</g>
</g>
<g>
<g class="p-tuft" fill="var(--p-dark)">
<path d="M190 46 C184 34 188 22 200 16 C198 28 204 34 206 46 Z"/>
<path d="M204 46 C204 32 214 22 228 20 C222 30 224 38 220 46 Z"/>
</g>
<path d="M200 140 C188 128 150 124 134 144 C118 166 130 208 172 224 C188 230 212 230 228 224 C270 208 282 166 266 144 C250 124 212 128 200 140 Z" fill="#FFFDF6"/>
<g>
<ellipse cx="160" cy="116" rx="26" ry="30" fill="#FFFFFF" stroke="var(--p-ink)" stroke-width="3"/>
<ellipse cx="164" cy="122" rx="12" ry="15" fill="#1B2230"/>
<circle cx="169" cy="115" r="5" fill="#FFFFFF"/>
<circle cx="158" cy="129" r="2.2" fill="#FFFFFF"/>
</g>
<g>
<ellipse cx="240" cy="116" rx="26" ry="30" fill="#FFFFFF" stroke="var(--p-ink)" stroke-width="3"/>
<ellipse cx="244" cy="122" rx="12" ry="15" fill="#1B2230"/>
<circle cx="249" cy="115" r="5" fill="#FFFFFF"/>
<circle cx="238" cy="129" r="2.2" fill="#FFFFFF"/>
</g>
<g>
<path d="M176 170 C190 174 210 174 224 170 C222 188 212 198 200 198 C188 198 178 188 176 170 Z" fill="#B8323F" stroke="#F0922A" stroke-width="6" stroke-linejoin="round"/>
<ellipse cx="200" cy="190" rx="9" ry="5" fill="#F06A7A"/>
<path d="M168 154 C172 138 228 138 232 154 C233 164 222 170 200 172 C178 170 167 164 168 154 Z" fill="#F7A530"/>
<path d="M182 148 C190 144 204 144 214 147" stroke="#FFD27A" stroke-width="4" stroke-linecap="round" fill="none"/>
</g>
</g>
<g transform="rotate(5 108 212)">
<path d="M96 196 C66 212 44 262 48 318 C50 340 62 350 74 340 C96 318 118 272 124 232 C126 214 116 200 96 196 Z" fill="var(--p-dark)"/>
<path d="M76 242 C64 272 60 304 66 328" stroke="var(--p-mid)" stroke-width="5" stroke-linecap="round" fill="none" opacity="0.6"/>
</g>
<g transform="translate(400 0) scale(-1 1)">
<g transform="rotate(5 108 212)">
<path d="M96 196 C66 212 44 262 48 318 C50 340 62 350 74 340 C96 318 118 272 124 232 C126 214 116 200 96 196 Z" fill="var(--p-dark)"/>
<path d="M76 242 C64 272 60 304 66 328" stroke="var(--p-mid)" stroke-width="5" stroke-linecap="round" fill="none" opacity="0.6"/>
</g>
</g>`,
  "one-wing": `<defs>
<clipPath id="bodyClip"><path d="M200 40 C262 40 304 86 304 148 C304 190 326 232 336 292 C346 360 322 440 262 456 C235 463 165 463 138 456 C78 440 54 360 64 292 C74 232 96 190 96 148 C96 86 138 40 200 40 Z"/></clipPath>
<clipPath id="bellyClip"><path d="M200 196 C252 196 286 246 292 306 C298 372 278 428 236 442 C220 447 180 447 164 442 C122 428 102 372 108 306 C114 246 148 196 200 196 Z"/></clipPath>
</defs>
<g>
<ellipse cx="200" cy="476" rx="128" ry="14" fill="var(--p-ink)" opacity="0.16"/>
</g>
<g>
<g transform="translate(146 468)">
<path d="M-40 10 C-44 -4 -30 -14 -12 -14 C6 -16 30 -10 40 2 C46 12 40 18 30 18 L-30 18 C-38 18 -41 14 -40 10 Z" fill="#B8693A"/>
<path d="M-24 -6 L-28 12 M-6 -10 L-8 14 M12 -8 L12 14" stroke="#8A4A26" stroke-width="3" stroke-linecap="round" fill="none"/>
</g>
<g transform="translate(254 468) scale(-1 1)">
<path d="M-40 10 C-44 -4 -30 -14 -12 -14 C6 -16 30 -10 40 2 C46 12 40 18 30 18 L-30 18 C-38 18 -41 14 -40 10 Z" fill="#B8693A"/>
<path d="M-24 -6 L-28 12 M-6 -10 L-8 14 M12 -8 L12 14" stroke="#8A4A26" stroke-width="3" stroke-linecap="round" fill="none"/>
</g>
</g>
<g>
<path d="M200 40 C262 40 304 86 304 148 C304 190 326 232 336 292 C346 360 322 440 262 456 C235 463 165 463 138 456 C78 440 54 360 64 292 C74 232 96 190 96 148 C96 86 138 40 200 40 Z" fill="var(--p-body)"/>
<g clip-path="url(#bodyClip)">
<path d="M262 42 C286 68 290 120 282 160 C278 202 306 240 308 296 C312 360 296 424 254 450 L420 480 L420 0 L262 0 Z" fill="var(--p-dark)" opacity="0.55"/>
<ellipse cx="148" cy="74" rx="34" ry="12" transform="rotate(-28 148 74)" fill="var(--p-light)" opacity="0.55"/>
</g>
<path d="M200 196 C252 196 286 246 292 306 C298 372 278 428 236 442 C220 447 180 447 164 442 C122 428 102 372 108 306 C114 246 148 196 200 196 Z" fill="#F8E7BE"/>
<g clip-path="url(#bellyClip)">
<ellipse cx="190" cy="476" rx="130" ry="56" fill="#E9CF98" opacity="0.6"/>
</g>
<g stroke="#E3C98C" stroke-width="3.5" stroke-linecap="round" fill="none">
<path d="M186 250 Q193 260 200 248"/>
<path d="M204 262 Q211 272 218 260"/>
<path d="M172 270 Q179 280 186 268"/>
</g>
</g>
<g>
<g class="p-tuft" fill="var(--p-dark)">
<path d="M190 46 C184 34 188 22 200 16 C198 28 204 34 206 46 Z"/>
<path d="M204 46 C204 32 214 22 228 20 C222 30 224 38 220 46 Z"/>
</g>
<path d="M200 140 C188 128 150 124 134 144 C118 166 130 208 172 224 C188 230 212 230 228 224 C270 208 282 166 266 144 C250 124 212 128 200 140 Z" fill="#FFFDF6"/>
<g>
<ellipse cx="160" cy="116" rx="26" ry="30" fill="#FFFFFF" stroke="var(--p-ink)" stroke-width="3"/>
<ellipse cx="164" cy="122" rx="12" ry="15" fill="#1B2230"/>
<circle cx="169" cy="115" r="5" fill="#FFFFFF"/>
<circle cx="158" cy="129" r="2.2" fill="#FFFFFF"/>
</g>
<g>
<ellipse cx="240" cy="116" rx="26" ry="30" fill="#FFFFFF" stroke="var(--p-ink)" stroke-width="3"/>
<ellipse cx="244" cy="122" rx="12" ry="15" fill="#1B2230"/>
<circle cx="249" cy="115" r="5" fill="#FFFFFF"/>
<circle cx="238" cy="129" r="2.2" fill="#FFFFFF"/>
</g>
<g>
<path d="M176 170 C190 174 210 174 224 170 C222 188 212 198 200 198 C188 198 178 188 176 170 Z" fill="#B8323F" stroke="#F0922A" stroke-width="6" stroke-linejoin="round"/>
<ellipse cx="200" cy="190" rx="9" ry="5" fill="#F06A7A"/>
<path d="M168 154 C172 138 228 138 232 154 C233 164 222 170 200 172 C178 170 167 164 168 154 Z" fill="#F7A530"/>
<path d="M182 148 C190 144 204 144 214 147" stroke="#FFD27A" stroke-width="4" stroke-linecap="round" fill="none"/>
</g>
</g>
<g transform="rotate(135 108 212)">
<path d="M96 196 C66 212 44 262 48 318 C50 340 62 350 74 340 C96 318 118 272 124 232 C126 214 116 200 96 196 Z" fill="var(--p-dark)"/>
<path d="M120 238 C112 280 94 316 72 338 C66 330 70 316 78 300 C94 270 102 250 104 226 Z" fill="#F8E7BE"/>
<path d="M76 242 C64 272 60 304 66 328" stroke="var(--p-mid)" stroke-width="5" stroke-linecap="round" fill="none" opacity="0.6"/>
</g>
<g transform="translate(400 0) scale(-1 1)">
<g transform="rotate(5 108 212)">
<path d="M96 196 C66 212 44 262 48 318 C50 340 62 350 74 340 C96 318 118 272 124 232 C126 214 116 200 96 196 Z" fill="var(--p-dark)"/>
<path d="M76 242 C64 272 60 304 66 328" stroke="var(--p-mid)" stroke-width="5" stroke-linecap="round" fill="none" opacity="0.6"/>
</g>
</g>`,
  "both-wings": `<defs>
<clipPath id="bodyClip"><path d="M200 40 C262 40 304 86 304 148 C304 190 326 232 336 292 C346 360 322 440 262 456 C235 463 165 463 138 456 C78 440 54 360 64 292 C74 232 96 190 96 148 C96 86 138 40 200 40 Z"/></clipPath>
<clipPath id="bellyClip"><path d="M200 196 C252 196 286 246 292 306 C298 372 278 428 236 442 C220 447 180 447 164 442 C122 428 102 372 108 306 C114 246 148 196 200 196 Z"/></clipPath>
</defs>
<g>
<ellipse cx="200" cy="476" rx="128" ry="14" fill="var(--p-ink)" opacity="0.16"/>
</g>
<g>
<g transform="translate(146 468)">
<path d="M-40 10 C-44 -4 -30 -14 -12 -14 C6 -16 30 -10 40 2 C46 12 40 18 30 18 L-30 18 C-38 18 -41 14 -40 10 Z" fill="#B8693A"/>
<path d="M-24 -6 L-28 12 M-6 -10 L-8 14 M12 -8 L12 14" stroke="#8A4A26" stroke-width="3" stroke-linecap="round" fill="none"/>
</g>
<g transform="translate(254 468) scale(-1 1)">
<path d="M-40 10 C-44 -4 -30 -14 -12 -14 C6 -16 30 -10 40 2 C46 12 40 18 30 18 L-30 18 C-38 18 -41 14 -40 10 Z" fill="#B8693A"/>
<path d="M-24 -6 L-28 12 M-6 -10 L-8 14 M12 -8 L12 14" stroke="#8A4A26" stroke-width="3" stroke-linecap="round" fill="none"/>
</g>
</g>
<g>
<path d="M200 40 C262 40 304 86 304 148 C304 190 326 232 336 292 C346 360 322 440 262 456 C235 463 165 463 138 456 C78 440 54 360 64 292 C74 232 96 190 96 148 C96 86 138 40 200 40 Z" fill="var(--p-body)"/>
<g clip-path="url(#bodyClip)">
<path d="M262 42 C286 68 290 120 282 160 C278 202 306 240 308 296 C312 360 296 424 254 450 L420 480 L420 0 L262 0 Z" fill="var(--p-dark)" opacity="0.55"/>
<ellipse cx="148" cy="74" rx="34" ry="12" transform="rotate(-28 148 74)" fill="var(--p-light)" opacity="0.55"/>
</g>
<path d="M200 196 C252 196 286 246 292 306 C298 372 278 428 236 442 C220 447 180 447 164 442 C122 428 102 372 108 306 C114 246 148 196 200 196 Z" fill="#F8E7BE"/>
<g clip-path="url(#bellyClip)">
<ellipse cx="190" cy="476" rx="130" ry="56" fill="#E9CF98" opacity="0.6"/>
</g>
<g stroke="#E3C98C" stroke-width="3.5" stroke-linecap="round" fill="none">
<path d="M186 250 Q193 260 200 248"/>
<path d="M204 262 Q211 272 218 260"/>
<path d="M172 270 Q179 280 186 268"/>
</g>
</g>
<g>
<g class="p-tuft" fill="var(--p-dark)">
<path d="M190 46 C184 34 188 22 200 16 C198 28 204 34 206 46 Z"/>
<path d="M204 46 C204 32 214 22 228 20 C222 30 224 38 220 46 Z"/>
</g>
<path d="M200 140 C188 128 150 124 134 144 C118 166 130 208 172 224 C188 230 212 230 228 224 C270 208 282 166 266 144 C250 124 212 128 200 140 Z" fill="#FFFDF6"/>
<g>
<ellipse cx="160" cy="116" rx="26" ry="30" fill="#FFFFFF" stroke="var(--p-ink)" stroke-width="3"/>
<ellipse cx="164" cy="122" rx="12" ry="15" fill="#1B2230"/>
<circle cx="169" cy="115" r="5" fill="#FFFFFF"/>
<circle cx="158" cy="129" r="2.2" fill="#FFFFFF"/>
</g>
<g>
<ellipse cx="240" cy="116" rx="26" ry="30" fill="#FFFFFF" stroke="var(--p-ink)" stroke-width="3"/>
<ellipse cx="244" cy="122" rx="12" ry="15" fill="#1B2230"/>
<circle cx="249" cy="115" r="5" fill="#FFFFFF"/>
<circle cx="238" cy="129" r="2.2" fill="#FFFFFF"/>
</g>
<g>
<path d="M176 170 C190 174 210 174 224 170 C222 188 212 198 200 198 C188 198 178 188 176 170 Z" fill="#B8323F" stroke="#F0922A" stroke-width="6" stroke-linejoin="round"/>
<ellipse cx="200" cy="190" rx="9" ry="5" fill="#F06A7A"/>
<path d="M168 154 C172 138 228 138 232 154 C233 164 222 170 200 172 C178 170 167 164 168 154 Z" fill="#F7A530"/>
<path d="M182 148 C190 144 204 144 214 147" stroke="#FFD27A" stroke-width="4" stroke-linecap="round" fill="none"/>
</g>
</g>
<g transform="rotate(128 108 212)">
<path d="M96 196 C66 212 44 262 48 318 C50 340 62 350 74 340 C96 318 118 272 124 232 C126 214 116 200 96 196 Z" fill="var(--p-dark)"/>
<path d="M120 238 C112 280 94 316 72 338 C66 330 70 316 78 300 C94 270 102 250 104 226 Z" fill="#F8E7BE"/>
<path d="M76 242 C64 272 60 304 66 328" stroke="var(--p-mid)" stroke-width="5" stroke-linecap="round" fill="none" opacity="0.6"/>
</g>
<g transform="translate(400 0) scale(-1 1)">
<g transform="rotate(128 108 212)">
<path d="M96 196 C66 212 44 262 48 318 C50 340 62 350 74 340 C96 318 118 272 124 232 C126 214 116 200 96 196 Z" fill="var(--p-dark)"/>
<path d="M120 238 C112 280 94 316 72 338 C66 330 70 316 78 300 C94 270 102 250 104 226 Z" fill="#F8E7BE"/>
<path d="M76 242 C64 272 60 304 66 328" stroke="var(--p-mid)" stroke-width="5" stroke-linecap="round" fill="none" opacity="0.6"/>
</g>
</g>`,
} as const;
