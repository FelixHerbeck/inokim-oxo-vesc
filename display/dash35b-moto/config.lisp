@const-start

(def config-metric-speeds true)
(def config-metric-temps true)

(def config-gnss-use-speed false) ; Prefer GPS speed over ESC speed
(def config-code-server true) ; Enable remote code execution

; Motorcycle-style full-screen view (views/view_moto.lbm). false = original views
(def config-moto-view true)
(def config-moto-kw-max 5.5)      ; power that fills the arc, kW
(def config-moto-utc-offset 2)    ; hours, for the clock (GPS time is UTC)
(def config-moto-dst-israel true) ; add an hour in Israeli summer time
(def config-moto-slope-sign 1.0)  ; -1.0 if the slope marker moves the wrong way

(def config-battery-hot 55.0) ; Displays warning indicator, Degrees C
(def config-esc-hot 80.0) ; Degrees C
(def config-motor-hot 80.0) ; Displays warning indicator, Degrees C

; Current limits for animation above speed dial
(def config-curr-accel 80.0)
(def config-curr-brake 60.0)

; Backlight levels
(def bl-lvl-bright 5)
(def bl-lvl-dim 1)

; Default light state
(def light-on-default false)

; Light-on means high beam, low beam otherwise
(def light-on-is-highbeam false)
