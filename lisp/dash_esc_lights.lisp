(import "pkg@://vesc_packages/lib_code_server/code_server.vescpkg" 'code-server)
(read-eval-program code-server)

(def light-on 0)

; Inokim OX light box settings
(def brake-light-threshold 1.0) ; ADC2 volts above which the brake counts as pulled
(def brake-flash 1)             ; 1 = flash while braking (like the original controller), 0 = steady (change live with setq)
(def brake-flash-period 0.1)    ; seconds on / seconds off while braking, if brake-flash = 1

; Automatic lights: DISABLED for now (no light sensor fitted).
; To enable later: uncomment these defs, the "AutoLight" thread and the
; auto-light condition in the "Lights" thread.
; LDR between AUX +5V (pin 1) and ADC3 (pin 8).
; The Duet's internal 10k pulldown completes the divider: dark = low voltage.
; Calibrate: read (get-adc 2) at dusk and set the thresholds around that value.
;(def auto-light-enabled 1)
;(def auto-light-on-v 1.0)       ; below this for auto-light-delay -> lights on
;(def auto-light-off-v 1.5)      ; above this for auto-light-delay -> lights off
;(def auto-light-delay 5.0)      ; seconds, avoids switching under bridges/trees
;(def auto-dark 0)
;(def dark-time 0.0)
;(def bright-time 0.0)
; ---- Motor winding temperature (no sensors in the hubs) ----
; A two-node heat model runs for both motors all the time:
;   winding + stator (Cw, J/K) <- copper loss 1.5*R(T)*(iq^2+id^2) + iron loss
;   winding -> shell/magnets through Rws (K/W)
;   shell (Cs, J/K) -> air through g0 + g1*km/h (W/K), so it cools better when moving
; One lumped node lags the winding on hard bursts (60 s at 90 A: 51 vs 67 degC),
; which is when the estimate matters. The constants are first estimates from the
; motor sizes and the 2026-11-04 logs, to be fitted from resistance measurements
; (tools/fit_thermal.py).
; Ambient = lowest Duet FET temperature seen since power-on.
; Power-on starts the model at ambient, which is wrong after a hot ride, so the
; first rear resistance measurement after power-on always resets the model
; (therm-boot-correct), whatever therm-meas-correct says.
; The rear winding is also measured directly by its resistance (copper +0.393 %/degC)
; at stops: standing still, throttle released, brake held for 2 s, at most once a
; minute. The measurement pushes 25 A through the stationary motor for ~0.3 s,
; the mechanical brake holds the wheel. Rear only: selecting motor 2 is global
; in LispBM and would redirect the other threads during the measurement.
; Above therm-limit-start (winding) or therm-shell-start (shell, magnets) the
; drive mode current scale is reduced linearly to therm-derate-min at the
; matching end temperature; the lower of the two wins.
; All of these can be changed live in the REPL with setq.
(def therm-cw1 900.0)      ; rear winding + stator heat capacity, J/K
(def therm-cs1 1600.0)     ; rear shell + magnets, J/K
(def therm-rws1 0.25)      ; rear winding -> shell, K/W
(def therm-g0-1 1.0)       ; rear shell -> air standing still, W/K
(def therm-g1-1 0.08)      ; rear shell -> air, extra W/K per km/h
(def therm-cw2 600.0)      ; front (stock 1500 W hub)
(def therm-cs2 1100.0)
(def therm-rws2 0.35)
(def therm-g0-2 0.8)
(def therm-g1-2 0.06)
(def therm-iron1 25.0)     ; iron loss in W at 55 km/h, scales with speed^1.5
(def therm-iron2 15.0)
(def therm-limit-start 100.0) ; degC winding, derating starts
(def therm-limit-end 125.0)   ; degC winding, derating reaches therm-derate-min
(def therm-shell-start 80.0)  ; degC shell (magnets), derating starts
(def therm-shell-end 100.0)
(def therm-boot-correct 1)    ; 1 = first measurement after power-on resets the model
(def therm-derate-min 0.3)    ; never below this, so there is always power to get home
(def therm-meas-enable 1)     ; 1 = measure rear resistance at stops
(def therm-meas-correct 0)    ; 1 = reset the rear model to each measurement (enable after checking logs)
(def therm-meas-current 25.0) ; A
(def therm-meas-samples 2000)
(def therm-meas-interval 60.0); s between measurements
(def therm-throttle-idle 0.55); ADC1 volts below which the throttle counts as released
(def therm-alpha 0.00393)

(def therm-r0 0.0564)  ; rear reference resistance (eeprom 100, set by therm-cal)
(def therm-t0 25.0)    ; temperature at therm-r0 (eeprom 101)
(def therm-r0-2 0.0373); front, from its motor config at startup
(def therm-t0-2 25.0)
(def therm-amb 25.0)
(def therm-t1 25.0)    ; rear winding, model
(def therm-t2 25.0)    ; front winding, model
(def therm-s1 25.0)    ; rear shell, model
(def therm-s2 25.0)    ; front shell, model
(def therm-p1 0.0)     ; rear loss, W
(def therm-p2 0.0)
(def therm-tmax 25.0)
(def therm-smax 25.0)
(def therm-booted 0)   ; set once the first measurement after power-on is done
(def therm-cooldown-on 0) ; set while therm-cooldown runs, keeps the stop measurement out
(def therm-meas-t 0.0) ; rear winding, last measurement
(def therm-meas-r 0.0) ; Ohm, last measurement
(def therm-meas-n 0)
(def therm-meas-ts 0)
(def therm-still 0.0)
(def therm-ts 0)
(def therm-derate 1.0)

(def drive-mode 1)
(def val-brk 0.0)
(def volts-brk 0.0)

; 2 is buttons only, 3 is buttons and ADC. Initially only
; the buttons are detached, but once throttle is received
; ADC2 is detached and replaced by the dash16 throttle
(def adc-detach-mode 2)

(def cruise-on 0)
(def cruise-ts 0)

(def battery-a-charging false)
(def battery-a-chg-time 0.0)
(def stats-battery-ah 0.0)

(def log-running false)
(def last-can-id -1)

; Limits most recently pushed by set-profile, nil until the first one
(def profile-last nil)

; Current scales and erpm limits as configured, captured at startup before a
; display can override them, so they can be put back if it goes away
(def limits-stored nil)

; systime of the last drive-mode frame from a display
(def display-ts 0)

; systime of the last drive mode change, used to hold a new mode briefly
(def mode-ts 0)

; Service switch. While this is set the drive profile is not applied, so the
; configured limits are the live ones and the controller can be tuned with the
; displays still connected. Current based measurements -- motor detection above
; all -- are wrong if a current scale is applied while they run, so there has to
; be a way to put the real limits back without unplugging anything.
;
; Deliberately not stored: a power cycle always clears it. Left set, a rider
; would have no mode limiting and neutral would not hold the throttle shut.
(def profile-suspend false)

; Set when the stored motor parameters cannot describe a real motor
(def motor-config-bad false)

; True when the suspension above was not asked for by anyone, so it can be
; lifted again without undoing a deliberate one
(def suspend-auto false)

; Drive mode at the moment the profile was suspended on its own
(def suspend-mode 1)

; What the limit capture saw, for checking on a bench
(def capture-dbg nil)

@const-start

; Provides ext-cmd-proc
(def lib-cmd-proc [
    0x00 0x00 0x00 0x00 0x08 0xb5 0x07 0x4b 0x07 0x49 0x08 0x48 0x7b 0x44 0x79 0x44 0x1b 0x68 0x03 0x4b
    0x78 0x44 0x1b 0x68 0x98 0x47 0x01 0x20 0x08 0xbd 0x00 0xbf 0x00 0xf8 0x00 0x10 0xf0 0xff 0xff 0xff
    0x2f 0x00 0x00 0x00 0x18 0x00 0x00 0x00 0x65 0x78 0x74 0x2d 0x63 0x6d 0x64 0x2d 0x70 0x72 0x6f 0x63
    0x00 0x00 0x00 0x00 0x01 0x29 0x38 0xb5 0x05 0x46 0x0b 0x4c 0x02 0xd0 0xd4 0xf8 0x90 0x00 0x38 0xbd
    0x63 0x6f 0x00 0x68 0x98 0x47 0x00 0x28 0xf7 0xd0 0xa3 0x6a 0x28 0x68 0x98 0x47 0xd4 0xf8 0x4c 0x32
    0xd0 0xe9 0x00 0x10 0x00 0x22 0x98 0x47 0xd4 0xf8 0x8c 0x00 0xed 0xe7 0x00 0xbf 0x00 0xf8 0x00 0x10
])

(defun set-profile (i-min i-max s-min s-max) {
        ; Every drive-mode frame from the display lands here, ten times a
        ; second. Neutral holds the throttle shut with a max scale of 0, so the
        ; profile has to keep being enforced, but rewriting the configuration
        ; at that rate fights anything else writing it -- motor detection above
        ; all. So write only when it is needed: the profile changed, or
        ; something has moved the scales out from under it.
        ; Motor temperature derating scales the drive mode's max current
        (var i-max-d (* i-max therm-derate))
        (var profile (list i-min i-max-d s-min s-max))

        (if (and (not profile-suspend)
                 (or (not (eq profile profile-last))
                     (not (= (conf-get 'l-current-min-scale) i-min))
                     (not (= (conf-get 'l-current-max-scale) i-max-d)))) {
                (setq profile-last profile)

                (var txb (bufcreate 37))
                (bufset-u8 txb 0 49) ; COMM_SET_MCCONF_TEMP_SETUP
                (bufset-u8 txb 1 0) ; Store
                (bufset-u8 txb 2 1) ; FWD CAN
                (bufset-u8 txb 3 0) ; ack
                (bufset-u8 txb 4 0) ; Divide by controllers
                (bufset-f32 txb 5 i-min)
                (bufset-f32 txb 9 i-max-d)
                (bufset-f32 txb 13 s-min)
                (bufset-f32 txb 17 s-max)
                (bufset-f32 txb 21 (conf-get 'l-min-duty))
                (bufset-f32 txb 25 (conf-get 'l-max-duty))
                (bufset-f32 txb 29 (conf-get 'l-watt-min))
                (bufset-f32 txb 33 (conf-get 'l-watt-max))
                (ext-cmd-proc txb)
        })
})

; Put the configured limits back after a display goes away. Without this the
; profile stays applied until the next power cycle, and motor detection run in
; that state stores the profile as if it were the real configuration.
; A detection run with a drive profile applied measures with the current
; scaled down, and can store a flux linkage of -2000. The motor then will not
; run at all and nothing anywhere says why. Only values that are never valid
; for any motor are flagged, so an unusual one cannot trip this.
(defun motor-config-check () {
        (setq motor-config-bad (or
            (<= (conf-get 'foc-motor-flux-linkage) 0.0)
            (<= (conf-get 'foc-motor-r) 0.0)
            (<= (conf-get 'foc-motor-l) 0.0)
        ))
})

(defun profile-suspend-set (on) {
        (setq profile-suspend (not-eq on 0))
        (setq suspend-auto false)

        (if profile-suspend
            (if limits-stored
                ; Put the configured limits back exactly
                (restore-limits)
                ; No baseline to restore, which is the normal state until the
                ; controller has been through a power cycle since installing.
                ; Suspending still has to mean "no scaling", so at least take
                ; the scales out of the picture. The speed limit is left alone
                ; because nothing here knows what it should be.
                {
                    (conf-set 'l-current-min-scale 1.0)
                    (conf-set 'l-current-max-scale 1.0)
                })
        )

        (setq profile-last nil)
        profile-suspend
})

; Record the live limits as the ones to restore. Only meaningful while the
; profile is suspended, because otherwise the live values are a drive profile
; and adopting those is the very thing that corrupts a setup. This is the
; reliable way to set the baseline -- the capture at startup can only guess,
; and has to refuse whenever it cannot trust what it reads.
(defun limits-capture () {
        (if (not profile-suspend)
            (print "Suspend drive profiles first, so the live limits are the real ones")
            {
                (setq limits-stored (list
                    (conf-get 'l-current-min-scale)
                    (conf-get 'l-current-max-scale)
                    (conf-get 'l-min-erpm)
                    (conf-get 'l-max-erpm)
                ))
                (print "Limits captured")
            })
        limits-stored
})

(defun restore-limits () {
        (conf-set 'l-current-min-scale (ix limits-stored 0))
        (conf-set 'l-current-max-scale (ix limits-stored 1))
        (conf-set 'l-min-erpm (ix limits-stored 2))
        (conf-set 'l-max-erpm (ix limits-stored 3))
        (setq profile-last nil)
})

(defmacro run-m2 (code) `(atomic {
            (var res nil)
            (select-motor 2)
            (setq res ,code)
            (select-motor 1)
            res
}))

(defun has-dual-motors () {
        (atomic
            (var motor-before (get-selected-motor))
            (select-motor 2)
            (var res (= (get-selected-motor) 2))
            (select-motor motor-before)
            res
        )
})

(def dual-motors (has-dual-motors))

; ---- Motor winding temperature functions ----
; One step of the two-node model. Returns (winding shell loss-W).
(defun therm-step (tw ts r0 t0 cw cs rws g0 g1 iron iq id kmh dt) {
        (var r (* r0 (+ 1.0 (* therm-alpha (- tw t0)))))
        (var v (abs kmh))
        (var s (/ v 55.0))
        (var p (+ (* 1.5 r (+ (* iq iq) (* id id))) (* iron s (sqrt s))))
        (var q (/ (- tw ts) rws))
        (list
            (+ tw (/ (* dt (- p q)) cw))
            (+ ts (/ (* dt (- q (* (- ts therm-amb) (+ g0 (* g1 v))))) cs))
            p)
})

; Front rise relative to rear, used only to seed the front model from a rear
; measurement after power-on. The front carried about half the rear's copper
; loss on 2026-11-04; 0.7 errs warm.
(def therm-front-ratio 0.7)

; Put both models at a measured rear winding temperature
(defun therm-reset-to (t-meas) {
        (setq therm-t1 t-meas)
        (setq therm-s1 t-meas)
        (var t-f (+ therm-amb (* therm-front-ratio (- t-meas therm-amb))))
        (if (> t-f therm-t2) {
                (setq therm-t2 t-f)
                (setq therm-s2 t-f)
        })
})

(defun therm-temp-from-r (r)
    (+ therm-t0 (/ (- (/ r therm-r0) 1.0) therm-alpha)))

(defun therm-can-measure ()
    (and (= therm-meas-enable 1)
         (= therm-cooldown-on 0)
         (not profile-suspend)
         (not motor-config-bad)
         (= cruise-on 0)
         (< (abs (get-speed)) 0.1)
         (< (abs (run-m2 (get-speed))) 0.1)
         (< (get-adc 0) therm-throttle-idle)
         (> (get-adc 1) brake-light-threshold)))

; One rear resistance measurement in Ohm, -1 on failure
(defun therm-measure-r ()
    (conf-measure-res therm-meas-current therm-meas-samples))

; REPL test, wheel in the air or brake held: (therm-test)
(defun therm-test () {
        (var r (therm-measure-r))
        (print (list "R mOhm" (* r 1000.0) "winding degC" (therm-temp-from-r r) "FET degC" (get-temp-fet)))
        r
})

; REPL calibration with a COLD motor (scooter parked for some hours), brake held
; or wheel in the air: (therm-cal). Averages 5 measurements and stores them with
; the FET temperature as the reference.
(defun therm-cal () {
        (var sum 0.0)
        (var n 0)
        (looprange i 0 5 {
                (var r (therm-measure-r))
                (if (> r 0.0) {
                        (setq sum (+ sum r))
                        (setq n (+ n 1))
                })
                (sleep 0.5)
        })
        (if (> n 2) {
                (setq therm-r0 (/ sum n))
                (setq therm-t0 (get-temp-fet))
                (eeprom-store-f 100 therm-r0)
                (eeprom-store-f 101 therm-t0)
                (print (list "Calibrated R0 mOhm" (* therm-r0 1000.0) "at degC" therm-t0))
            }
            (print "Calibration failed"))
})

(defun therm-init () {
        (var er (eeprom-read-f 100))
        (var et (eeprom-read-f 101))
        (if (and er et (> er 0.02) (< er 0.2) (> et -20.0) (< et 60.0))
            {
                (setq therm-r0 er)
                (setq therm-t0 et)
            }
            {
                (setq therm-r0 (conf-get 'foc-motor-r))
                (setq therm-t0 25.0)
            })
        (if dual-motors (setq therm-r0-2 (run-m2 (conf-get 'foc-motor-r))))
        (setq therm-amb (get-temp-fet))
        (setq therm-t1 therm-amb)
        (setq therm-t2 therm-amb)
        (setq therm-s1 therm-amb)
        (setq therm-s2 therm-amb)
        (setq therm-tmax therm-amb)
        (setq therm-smax therm-amb)
        (setq therm-ts (systime))
})

; Linear derating factor between start and end temperature
(defun therm-scale (temp t-start t-end) {
        (var d (- 1.0 (/ (* (- 1.0 therm-derate-min) (- temp t-start)) (- t-end t-start))))
        (if (> d 1.0) (setq d 1.0))
        (if (< d therm-derate-min) (setq d therm-derate-min))
        d
})

(defun therm-loop () {
        (var dt (secs-since therm-ts))
        (setq therm-ts (systime))
        (if (> dt 1.0) (setq dt 1.0))
        (var kmh (* (get-speed) 3.6))

        ; Ambient: the FET reads warm right after a ride, so keep the lowest value
        (var fet (get-temp-fet))
        (if (< fet therm-amb) (setq therm-amb fet))

        (var m1 (therm-step therm-t1 therm-s1 therm-r0 therm-t0
                therm-cw1 therm-cs1 therm-rws1 therm-g0-1 therm-g1-1 therm-iron1
                (get-iq 1) (get-id 1) kmh dt))
        (setq therm-t1 (ix m1 0))
        (setq therm-s1 (ix m1 1))
        (setq therm-p1 (ix m1 2))
        (if dual-motors {
                (var m2 (therm-step therm-t2 therm-s2 therm-r0-2 therm-t0-2
                        therm-cw2 therm-cs2 therm-rws2 therm-g0-2 therm-g1-2 therm-iron2
                        (run-m2 (get-iq 1)) (run-m2 (get-id 1)) kmh dt))
                (setq therm-t2 (ix m2 0))
                (setq therm-s2 (ix m2 1))
                (setq therm-p2 (ix m2 2))
        })
        (setq therm-tmax (if (> therm-t1 therm-t2) therm-t1 therm-t2))
        (setq therm-smax (if (> therm-s1 therm-s2) therm-s1 therm-s2))

        ; Derating in steps of 0.05, so the configuration is not rewritten constantly
        (var dw (therm-scale therm-tmax therm-limit-start therm-limit-end))
        (var ds (therm-scale therm-smax therm-shell-start therm-shell-end))
        (var d (if (< dw ds) dw ds))
        (setq therm-derate (/ (to-i (* d 20.0)) 20.0))

        ; Resistance measurement at stops
        (if (therm-can-measure)
            (setq therm-still (+ therm-still dt))
            (setq therm-still 0.0))
        (if (and (> therm-still 2.0) (> (secs-since therm-meas-ts) therm-meas-interval)) {
                (var r (therm-measure-r))
                (setq therm-meas-ts (systime))
                (setq therm-still 0.0)
                (if (and (> r (* therm-r0 0.8)) (< r (* therm-r0 1.6))) {
                        (setq therm-meas-r r)
                        (setq therm-meas-t (therm-temp-from-r r))
                        (setq therm-meas-n (+ therm-meas-n 1))
                        (if (or (= therm-meas-correct 1)
                                (and (= therm-boot-correct 1) (= therm-booted 0)))
                            (therm-reset-to therm-meas-t))
                        (setq therm-booted 1)
                })
        })
})

; REPL, for the cooldown curve after a hot ride: (therm-cooldown 40 60.0)
; measures the rear resistance every period seconds, n times, while logging runs.
; Rear wheel off the ground, or brake held: the DC test current pulls the rotor
; to the nearest pole, a small jerk. Stops if the scooter moves or the throttle
; is touched. Each result lands in the log (Wind M1 meas) and is printed.
(defun therm-cooldown (n period) {
        (var t-start (systime))
        (var i 0)
        (setq therm-cooldown-on 1)
        (loopwhile (< i n) {
                (if (or (> (abs (get-speed)) 0.1) (> (get-adc 0) therm-throttle-idle)) {
                        (print "Stopped: moving or throttle")
                        (setq i n)
                    } {
                        (var r (therm-measure-r))
                        (if (> r 0.0) {
                                (setq therm-meas-r r)
                                (setq therm-meas-t (therm-temp-from-r r))
                                (setq therm-meas-ts (systime))
                                (setq therm-meas-n (+ therm-meas-n 1))
                                (print (list "s" (to-i (secs-since t-start))
                                    "meas" therm-meas-t "model" therm-t1 "shell" therm-s1
                                    "FET" (get-temp-fet)))
                        })
                        (setq i (+ i 1))
                        (if (< i n) (sleep period))
                })
        })
        (setq therm-cooldown-on 0)
})

(defun proc-sid (id data) {
        (cond
            ((= id 35) {
                    (setq battery-a-charging (= (bufget-u8 data 2) 1))
                    (setq battery-a-chg-time (bufget-u16 data 3))
                    (setq stats-battery-ah (/ (bufget-u16 data 5) 10.0))
            })

            ((= id 201) {
                    (setq display-ts (systime))
                    (var drive-mode-new (bufget-u8 data 0))
                    (setq light-on (bufget-u8 data 1))

                    ; A second display that has not caught up yet keeps sending
                    ; the previous mode for a frame or two. Hold a new mode
                    ; briefly so the limits cannot flick between two modes while
                    ; the others catch up.
                    (if (and (!= drive-mode-new drive-mode)
                             (< (secs-since mode-ts) 0.3))
                        (setq drive-mode-new drive-mode))

                    (if (!= drive-mode drive-mode-new) {
                            (setq cruise-on 0)
                            (setq mode-ts (systime))
                    })

                    (setq drive-mode drive-mode-new)

                    (match drive-mode
                        (0 { ; Reverse
                                (set-profile
                                    (read-setting 'mode-r-current-brk)
                                    (read-setting 'mode-r-current)
                                    (/ (read-setting 'mode-r-speed) -3.6)
                                    (/ (read-setting 'mode-1-speed) 3.6)
                                )

                                (app-adc-override 2 1)
                                (app-adc-detach adc-detach-mode (read-setting 'throttle-mode))
                        })
                        (1 { ; Neutral
                                (set-profile
                                    (read-setting 'mode-n-current-brk)
                                    0
                                    (/ (read-setting 'mode-1-speed) -3.6)
                                    (/ (read-setting 'mode-1-speed) 3.6)
                                )

                                (app-adc-override 2 0)
                                (app-adc-detach adc-detach-mode (read-setting 'throttle-mode))
                        })
                        (2 { ; 1
                                (set-profile
                                    (read-setting 'mode-1-current-brk)
                                    (read-setting 'mode-1-current)
                                    (/ (read-setting 'mode-1-speed) -3.6)
                                    (/ (read-setting 'mode-1-speed) 3.6)
                                )

                                (app-adc-override 2 0)
                                (app-adc-detach adc-detach-mode (read-setting 'throttle-mode))
                        })
                        (3 { ; 2
                                (set-profile
                                    (read-setting 'mode-2-current-brk)
                                    (read-setting 'mode-2-current)
                                    (/ (read-setting 'mode-2-speed) -3.6)
                                    (/ (read-setting 'mode-2-speed) 3.6)
                                )

                                (app-adc-override 2 0)
                                (app-adc-detach adc-detach-mode (read-setting 'throttle-mode))
                        })
                        (4 { ; 3
                                (set-profile
                                    (read-setting 'mode-3-current-brk)
                                    (read-setting 'mode-3-current)
                                    (/ (read-setting 'mode-3-speed) -3.6)
                                    (/ (read-setting 'mode-3-speed) 3.6)
                                )

                                (app-adc-override 2 0)
                                (app-adc-detach adc-detach-mode (read-setting 'throttle-mode))
                        })
                    )

                    ; Inokim light box: AUX 2 (switched VBUS) now powers the
                    ; light box permanently (see "Lights" thread in main), so
                    ; only the 12V AUX 1 output follows the lights button.
                    (if (= light-on 1)
                        (set-aux 1 1)
                        (set-aux 1 0)
                    )
            })

            ((= id 203) {
                    (setq val-brk (/ (bufget-i16 data 0) 1000.0))
                    (setq volts-brk (/ (bufget-i16 data 2) 1000.0))

                    (setq adc-detach-mode 3)

                    (if (= (read-setting 'throttle-mode) 2)
                        (app-adc-override 0 volts-brk)
                        (app-adc-override 1 volts-brk)
                    )

                    (app-adc-detach adc-detach-mode (read-setting 'throttle-mode)) ; Detach ADC2
            })

            ; Event
            ((= id 250) {
                    (cond
                        ((= (bufget-u8 data 0) 0) { ; Toggle cruise control
                                (setq cruise-on (if (= cruise-on 0) 1 0))
                                (if (= cruise-on 1) (setq cruise-ts (systime)))
                        })

                        ((= (bufget-u8 data 0) 2) { ; Toggle logging
                                (if log-running
                                    (stop-log (read-setting 'can-id))
                                    (start-log
                                        (read-setting 'can-id)
                                        (read-setting 'append-gnss)
                                        (read-setting 'log-local)
                                        (read-setting 'log-can)
                                        (read-setting 'log-bms)
                                        (read-setting 'log-rate)
                                    )
                                )
                        })

                        ((= (bufget-u8 data 0) 1) { ; About to turn off
                                ; Close the log while there is still power. The
                                ; firmware's own shutdown event does this too,
                                ; but it does not fire when the display cuts
                                ; power itself, which would leave the last
                                ; records unwritten.
                                (if log-running (stop-log last-can-id))

                                ; Put the configured limits back first. This
                                ; stores the motor configuration, and with a
                                ; drive profile applied conf-store would write
                                ; the profile's scales and speed limits into it
                                ; as though they were the real settings.
                                (if limits-stored (restore-limits))

                                ; Only store once the limits are known to be the
                                ; real ones: either they were just put back, or
                                ; no profile has been applied at all. Without a
                                ; trustworthy baseline this would write whatever
                                ; drive profile is active in as the configuration,
                                ; which is the very thing that corrupts a setup.
                                ; Losing one backup beats that.
                                (if (or limits-stored (eq profile-last nil))
                                    ; store-backup is very new, so fall back to conf-store
                                    ; if it does not exist using trap
                                    (match (trap (store-backup))
                                        ((exit-ok (? a)) t)
                                        (_ (conf-store))
                                    )
                                    (print "Limits unknown, not storing configuration")
                                )
                        })
                    )
            })
        )
})

(defun event-handler ()
    (loopwhile t
        (recv
            ((event-data-rx . (? data)) (trap (eval (read data))))
            (event-shutdown (stop-log last-can-id))
            ((event-can-sid . ((? id) . (? data))) (trap (proc-sid id data)))
            (_ nil)
)))

; Local data to log
;
; Format
; (optKey optName optUnit optPrecision optIsRel optIsTime value-function)
;
; All entries except value-function are optional and
; default values will be used if they are left out.
(def loglist-local '(
        ("Input Voltage" "V"            (get-vin))
        ("Current" "A"                  (get-current 1))
        ("Current In" "A"               (get-current-in 1))
        ("Duty"                         (get-duty))
        ("RPM"                          (get-rpm))
        ("Temp Fet" "degC" 1            (get-temp-fet))
        ("Temp Motor" "degC" 1          (get-temp-mot))
        ("Batt" "%"                     (* (get-batt) 100))
        ("kmh_vesc" "km/h" "Speed VESC" (* (get-speed) 3.6))
        ("roll"                         (ix (get-imu-rpy) 0))
        ("pitch"                        (ix (get-imu-rpy) 1))
        ("yaw"                          (ix (get-imu-rpy) 2))
        ("fault"                        (get-fault))
        ("trip_vesc" "m"                (get-dist))
        ("trip_vesc_abs" "m"            (get-dist-abs))
        ("cnt_ah" "Ah" "Amp Hours"      (get-ah))
        ("cnt_wh" "Wh" "Watt Hours"     (get-wh))
        ("cnt_ah_chg" "Ah" "Ah Chg"     (get-ah-chg))
        ("cnt_wh_chg" "Wh" "Wh Chg"     (get-wh-chg))
        ("ADC1" "V"                     (get-adc 0))
        ("ADC2" "V"                     (get-adc 1))
        ("iq" "A"                       (get-iq 1))
        ("id" "A"                       (get-id 1))
        ("vq" "V"                       (get-vq 1))
        ("vd" "V"                       (get-vd 1))
        ("Fault"                        (get-fault))
        ("Drive Mode"                   (+ drive-mode 0))
))

; CAN-data template. Same format as above, but all %d in strings will
; be replaced with can-id. Id in the last field will also be replaced
; with can id.
(def loglist-can-template '(
        ("V%d Current" "A"              (canget-current id))
        ("V%d Current In" "A"           (canget-current-in id))
        ("V%d Duty"                     (canget-duty id))
        ("V%d RPM"                      (canget-rpm id))
        ("V%d Temp Fet" "degC" 1        (canget-temp-fet id))
        ("V%d Temp Motor" "degC" 1      (canget-temp-motor id))
        ("V%d ADC1" "V"                 (canget-adc id 0))
        ("V%d ADC2" "V"                 (canget-adc id 1))
        ("V%d Input Voltage" "V"        (canget-vin id))
))

(defun merge-lists (list-with-lists) (foldl append () list-with-lists))

; Scan CAN-bus and make loglists for all devices
(defun canlist-create ()
    (merge-lists
        (map
            (fn (id) ; For every CAN ID
                (map
                    (fn (row) ; For every row in template
                        (map
                            (fn (e) ; For every element in that row
                                (cond
                                    ((eq (type-of e) type-array) (str-from-n id e))
                                    ((eq (type-of e) type-list) (map (fn (x) (if (eq x 'id) id x)) e))
                                    (true e)
                                )
                            )
                            row
                        )
                    )
                    loglist-can-template
                )
            )
            (can-list-devs)
        )
    )
)

(defun bmslist-create()
    (let (
            (res ())
            (add (fn (x) (setvar 'res (append res (list x)))))
        )
        (if (< (get-bms-val 'bms-msg-age) 2)
            (progn
                (add '("bms_v_tot" "V" "BMS Voltage" (get-bms-val 'bms-v-tot)))
                (looprange i 0 (get-bms-val 'bms-cell-num)
                    (add (list (str-from-n (+ i 1) "BMS_C%d") "V" 3 (list 'get-bms-val ''bms-v-cell i)))
                )
                (add '("bms_i_in_ic" "A" "BMS Current" (get-bms-val 'bms-i-in-ic)))
                (add '("bms_soc" "%" "BMS SOC" (* (get-bms-val 'bms-soc) 100.0)))
                (add '("bms_hum" "%" "BMS Hum" (get-bms-val 'bms-hum)))
                (add '("bms_temp_hum" "degC" "BMS Temp Hum" (get-bms-val 'bms-temp-hum)))
                (looprange i 0 (get-bms-val 'bms-temp-adc-num)
                    (add (list (str-from-n (+ i 1) "BMS_T%d") "degC" 3 (list 'get-bms-val ''bms-temps-adc i)))
                )
                res
            )
            res

)))

(defun loglist-parse (id lst res-fun)
    (looprange row 0 (length lst)
        (let (
                (field (ix lst row))
                (get-field
                    (fn (type default)
                        (let ((f (first field)))
                            (if (eq (type-of f) type)
                                (progn
                                    (setvar 'field (rest field))
                                    f
                                )
                                default
                ))))
                (key       (get-field type-array (str-from-n row "Field %d")))
                (unit      (get-field type-array ""))
                (name      (get-field type-array key))
                (precision (get-field type-i 2))
                (is-rel    (get-field type-symbol false))
                (is-time   (get-field type-symbol false))
            )
            (res-fun
                id ; CAN id
                row ; Field
                key ; Key
                name ; Name
                unit ; Unit
                precision ; Precision
                is-rel ; Is relative
                is-time ; Is timestamp
            )
)))

; Confiure all log fields based on loglist lst
(defun log-configure (id lst) (loglist-parse id lst 'log-config-field))

; Print all parsed fields of loglist lst
(defun print-loglist (lst) (loglist-parse 0 lst
        (fn (id row key name unit precision is-rel is-time)
            (print (list key name unit precision is-rel is-time (ix (ix lst row) -1)))
)))

(defun log-thd (id rate lst)
    (loopwhile log-running
        (progn
            (log-send-f32 id 0
                (map
                    (fn (x) (eval (ix x -1)))
                    lst
                )
            )
            (sleep (/ 1.0 rate))
)))

(defun start-log (id append-gnss log-local log-can log-bms rate)
    (progn
        (def last-can-id id)
        (stop-log id)

        (def loglist (merge-lists
                (list
                    (if log-local loglist-local ())
                    (if log-can (canlist-create) ())
                    (if log-bms (bmslist-create) ())
        )))

        (if (eq loglist nil)
            (send-msg "Nothing to log. Make sure that everything on the CAN-bus has status messages enabled.")

            (progn
                (log-configure id loglist)

                (log-start
                    id ; CAN id
                    (length loglist) ; Field num
                    rate ; Rate Hz
                    true ; Append time
                    append-gnss ; Append gnss
                )

                (def log-running true)
                (def log-thd-id (spawn log-thd id rate loglist))
                (send-data "Log Started")
        ))
))

(defun stop-log (id) {
        (log-stop id)
        (if log-running {
                (def log-running false)
                (wait log-thd-id)
                (send-data "Log stopped")
        })
})

(defun save-config () {
        (write-setting 'can-id (rest-args 0))
        (write-setting 'append-gnss (rest-args 1))
        (write-setting 'log-local (rest-args 2))
        (write-setting 'log-can (rest-args 3))
        (write-setting 'log-bms (rest-args 4))
        (write-setting 'log-rate (rest-args 5))
        (write-setting 'log-at-boot (rest-args 6))
        (write-setting 'throttle-mode (rest-args 7))
        (send-data "Settings Saved!")
})

(defun save-modes () {
        (write-setting 'mode-r-speed (rest-args 0))
        (write-setting 'mode-r-current (rest-args 1))
        (write-setting 'mode-r-current-brk (rest-args 2))
        (write-setting 'mode-n-current-brk (rest-args 3))
        (write-setting 'mode-1-speed (rest-args 4))
        (write-setting 'mode-1-current (rest-args 5))
        (write-setting 'mode-1-current-brk (rest-args 6))
        (write-setting 'mode-2-speed (rest-args 7))
        (write-setting 'mode-2-current (rest-args 8))
        (write-setting 'mode-2-current-brk (rest-args 9))
        (write-setting 'mode-3-speed (rest-args 10))
        (write-setting 'mode-3-current (rest-args 11))
        (write-setting 'mode-3-current-brk (rest-args 12))
})

; Persistent settings
; Format: (label . (offset type))
(def eeprom-addrs '(
        (ver-code    . (0 i))
        (can-id      . (1 i))
        (log-at-boot . (2 b))
        (append-gnss . (3 b))
        (log-rate    . (4 f))
        (log-local   . (5 b))
        (log-can     . (6 b))
        (log-bms     . (7 b))

        (mode-r-speed       . (8 f))
        (mode-r-current     . (9 f))
        (mode-r-current-brk . (10 f))
        (mode-n-current-brk . (11 f))
        (mode-1-speed       . (12 f))
        (mode-1-current     . (13 f))
        (mode-1-current-brk . (14 f))
        (mode-2-speed       . (15 f))
        (mode-2-current     . (16 f))
        (mode-2-current-brk . (17 f))
        (mode-3-speed       . (18 f))
        (mode-3-current     . (19 f))
        (mode-3-current-brk . (20 f))

        (throttle-mode      . (21 i))
))

(defun print-settings ()
    (loopforeach it eeprom-addrs
        (print (list (first it) (read-setting (first it))))
))

; Settings version
(def settings-version 241i32)

(defun read-setting (name)
    (let (
            (addr (first (assoc eeprom-addrs name)))
            (type (second (assoc eeprom-addrs name)))
        )
        (cond
            ((eq type 'i) (eeprom-read-i addr))
            ((eq type 'f) (eeprom-read-f addr))
            ((eq type 'b) (!= (eeprom-read-i addr) 0))
)))

(defun write-setting (name val)
    (let (
            (addr (first (assoc eeprom-addrs name)))
            (type (second (assoc eeprom-addrs name)))
        )
        (cond
            ((eq type 'i) (eeprom-store-i addr val))
            ((eq type 'f) (eeprom-store-f addr val))
            ((eq type 'b) (eeprom-store-i addr (if val 1 0)))
)))

(defun restore-settings () {
        (write-setting 'can-id (if (eq (sysinfo 'hw-type) 'hw-express) -2 2))
        (write-setting 'log-at-boot false)
        (write-setting 'log-rate 10)
        (write-setting 'append-gnss false)
        (write-setting 'log-local true)
        (write-setting 'log-can true)
        (write-setting 'log-bms false)
        (write-setting 'ver-code settings-version)

        (write-setting 'mode-r-speed 15.0)
        (write-setting 'mode-r-current 0.5)
        (write-setting 'mode-r-current-brk 1.0)

        (write-setting 'mode-n-current-brk 1.0)

        (write-setting 'mode-1-speed 20.0)
        (write-setting 'mode-1-current 0.5)
        (write-setting 'mode-1-current-brk 1.0)

        (write-setting 'mode-2-speed 25.0)
        (write-setting 'mode-2-current 0.6)
        (write-setting 'mode-2-current-brk 1.0)

        (write-setting 'mode-3-speed 250.0)
        (write-setting 'mode-3-current 1.0)
        (write-setting 'mode-3-current-brk 1.0)

        (write-setting 'throttle-mode 3)
})

(defun send-settings ()
    (send-data (str-merge
            "settings "
            (str-from-n (read-setting 'can-id) "%d ")
            (if (read-setting 'log-at-boot) "1 " "0 ")
            (str-from-n (read-setting 'log-rate) "%.2f ")
            (if (read-setting 'append-gnss) "1 " "0 ")
            (if (read-setting 'log-local) "1 " "0 ")
            (if (read-setting 'log-can) "1 " "0 ")
            (if (read-setting 'log-bms) "1 " "0 ")
            (str-from-n (read-setting 'throttle-mode) "%d ")
)))

(defun send-modes ()
    (send-data (str-merge
            "modes "
            (str-from-n (read-setting 'mode-r-speed) "%.2f ")
            (str-from-n (read-setting 'mode-r-current) "%.2f ")
            (str-from-n (read-setting 'mode-r-current-brk) "%.2f ")
            (str-from-n (read-setting 'mode-n-current-brk) "%.2f ")
            (str-from-n (read-setting 'mode-1-speed) "%.2f ")
            (str-from-n (read-setting 'mode-1-current) "%.2f ")
            (str-from-n (read-setting 'mode-1-current-brk) "%.2f ")
            (str-from-n (read-setting 'mode-2-speed) "%.2f ")
            (str-from-n (read-setting 'mode-2-current) "%.2f ")
            (str-from-n (read-setting 'mode-2-current-brk) "%.2f ")
            (str-from-n (read-setting 'mode-3-speed) "%.2f ")
            (str-from-n (read-setting 'mode-3-current) "%.2f ")
            (str-from-n (read-setting 'mode-3-current-brk) "%.2f ")
)))

(defun send-msg (text)
    (send-data (str-merge "msg " text))
)

(defun main () {
        (set-print-prefix "ESC-")

        (if (has-dual-motors) {
                (setq loglist-local (append
                        loglist-local
                        '(
                            ("M2 Current" "A"                  (run-m2 (get-current)))
                            ("M2 Current In" "A"               (run-m2 (get-current-in)))
                            ("M2 Duty"                         (run-m2 (get-duty)))
                            ("M2 RPM"                          (run-m2 (get-rpm)))
                            ("M2 Temp Fet" "degC" 1            (run-m2 (get-temp-fet)))
                            ("M2 Temp Motor" "degC" 1          (run-m2 (get-temp-mot)))
                            ("M2 iq" "A"                       (run-m2 (get-iq)))
                            ("M2 id" "A"                       (run-m2 (get-id)))
                            ("M2 Fault"                        (run-m2 (get-fault)))
                        )
                ))
        })

        ; Motor winding temperature: model, rear measurement, derating
        (therm-init)
        (setq loglist-local (append
                loglist-local
                '(
                    ("Wind M1" "degC" 1                (+ therm-t1 0.0))
                    ("Wind M2" "degC" 1                (+ therm-t2 0.0))
                    ("Shell M1" "degC" 1               (+ therm-s1 0.0))
                    ("Shell M2" "degC" 1               (+ therm-s2 0.0))
                    ("Loss M1" "W"                     (+ therm-p1 0.0))
                    ("Loss M2" "W"                     (+ therm-p2 0.0))
                    ("Therm amb" "degC" 1              (+ therm-amb 0.0))
                    ("Wind M1 meas" "degC" 1           (+ therm-meas-t 0.0))
                    ("R M1 meas" "mOhm"                (* therm-meas-r 1000.0))
                    ("R M1 est" "mOhm"                 (* (get-est-res) 1000.0))
                    ("Therm derate"                    (+ therm-derate 0.0))
                )
        ))

        ; Restore settings if version number does not match
        ; as that probably means something else is in eeprom
        (if (not-eq (read-setting 'ver-code) settings-version) (restore-settings))

        ; Capture the configured limits, but only when they can be trusted.
        ; A temporary configuration outlives this package: reinstalling or
        ; restarting the script leaves the previous run's profile applied, so
        ; reading it then would capture the profile instead of the real
        ; limits. Just after the controller booted, nothing has overridden
        ; anything yet. The window is generous because this script is only
        ; parsed and run some way into startup, while restarting it by hand
        ; happens on a controller that has been up far longer.
        ;
        ; A max scale of zero is never a real setting, so refuse that: it is
        ; what neutral applies, and restoring it would leave the motor unable
        ; to make torque. Anything else a bad capture could pick up is one of
        ; the drive profiles, which is more restrictive than the real limits
        ; rather than less. Failing to capture at all only leaves
        ; restore-limits inactive until the next power cycle.
        (setq capture-dbg (list
            (secs-since 0)
            (conf-get 'l-current-min-scale)
            (conf-get 'l-current-max-scale)
            (conf-get 'l-max-erpm)
        ))

        (if (and (< (secs-since 0) 30.0)
                 (> (conf-get 'l-current-max-scale) 0.0))
            (setq limits-stored (list
                (conf-get 'l-current-min-scale)
                (conf-get 'l-current-max-scale)
                (conf-get 'l-min-erpm)
                (conf-get 'l-max-erpm)
            ))
        )

        (event-register-handler (spawn event-handler))
        (event-enable 'event-can-sid)
        (event-enable 'event-shutdown)
        (event-enable 'event-data-rx)

        (load-native-lib lib-cmd-proc)

        (var buf-can (array-create 8))

        (loopwhile-thd ("Send CAN" 150) t {
                (bufclear buf-can)
                (bufset-i16 buf-can 0 (* (get-batt) 1000))
                (bufset-i16 buf-can 2 (* (abs (get-duty)) 1000))
                (bufset-i16 buf-can 4 (* (abs (get-speed)) 3.6 10))
                (bufset-i16 buf-can 6 (* (setup-current-in) (get-vin) 0.1))
                (can-send-sid 20 buf-can)

                (bufclear buf-can)
                (if (> (get-bms-val 'bms-temp-adc-num) 2)
                    (bufset-i16 buf-can 0 (* (get-bms-val 'bms-temps-adc 2) 10))
                    (bufset-i16 buf-can 0 0)
                )
                (bufset-i16 buf-can 2 (* (get-temp-fet) 10))
                (bufset-i16 buf-can 4 (* therm-tmax 10)) ; no motor sensors: hottest modelled winding
                (bufset-i16 buf-can 6 (* (ix (get-imu-rpy) 1) 100))
                (can-send-sid 21 buf-can)

                (bufclear buf-can)
                (bufset-u16 buf-can 0 (* (setup-wh) 10.0))
                (bufset-u16 buf-can 2 (* (setup-wh-chg) 10.0))
                (bufset-u16 buf-can 4 (* (/ (get-dist-abs) 1000.0) 10))
                (bufset-u16 buf-can 6 (get-fault))
                (can-send-sid 22 buf-can)

                (bufclear buf-can)
                (if dual-motors
                    {
                        (bufset-u16 buf-can 0 (to-i (+ (stats 'stat-current-avg) (run-m2 (stats 'stat-current-avg)))))
                        (bufset-u16 buf-can 2 (to-i (+ (stats 'stat-current-max) (run-m2 (stats 'stat-current-max)))))
                        (bufset-i16 buf-can 4 (to-i (+ (get-current) (run-m2 (get-current)))))
                    }
                    {
                        (bufset-u16 buf-can 0 (to-i (stats 'stat-current-avg)))
                        (bufset-u16 buf-can 2 (to-i (stats 'stat-current-max)))
                        (bufset-i16 buf-can 4 (to-i (get-current)))
                    }
                )
                (bufset-u16 buf-can 6 (to-i (conf-get 'si-battery-ah)))
                (can-send-sid 23 buf-can)

                (bufclear buf-can)
                (bufset-u16 buf-can 0 (* (get-vin) 10))
                (bufset-u32 buf-can 2 (* (/ (sysinfo 'odometer) 1000.0) 10))
                (bufset-u16 buf-can 6 (* (abs (get-speed-set)) 3.6 10)) ; Cruise control speed
                ; Reserved space
                (can-send-sid 24 buf-can)

                (bufclear buf-can)
                (bufset-u8 buf-can 0 cruise-on)
                (can-send-sid 202 buf-can)

                ; Logging state on an id of its own. 202 also carries the
                ; wheelie settings the other way, and a display cannot tell a
                ; controller's frame from another display's.
                (bufclear buf-can)
                (bufset-u8 buf-can 0 (if log-running 1 0))
                ; The mode this controller is actually applying, so every
                ; display shows the same thing rather than its own idea of it
                (bufset-u8 buf-can 1 drive-mode)
                (bufset-u8 buf-can 2 (if profile-suspend 1 0))
                (bufset-u8 buf-can 3 (if motor-config-bad 1 0))
                (can-send-sid 25 buf-can)

                (sleep 0.1)
        })

        (loopwhile-thd ("Cruise" 150) t {
                (if (and (> (secs-since cruise-ts) 1) (< (* (abs (get-speed-set)) 3.6) 5.0)) {
                        (setq cruise-on 0)
                })

                (if (or
                        (< drive-mode 2)
                        (and (> (secs-since cruise-ts) 2) (> (abs (get-adc-decoded)) 0.05))
                    )
                    (setq cruise-on 0)
                )

                (app-adc-override 3 cruise-on)

                (sleep 0.05)
        })

        (loopwhile-thd ("Limits" 120) t {
                ; A display that goes away leaves its profile applied until the
                ; next power cycle. Put the configured limits back instead, so
                ; the controller is not left running a drive profile it is no
                ; longer being told about, and so motor detection done with the
                ; display unplugged sees the real configuration.
                ;
                ; Only while stopped: losing a display mid-ride must not hand
                ; the rider more power than the mode they were riding in.
                (motor-config-check)

                ; A motor whose parameters cannot describe a real motor will not
                ; turn at all, so lifting the drive profile cannot make it less
                ; safe -- and lifting it is exactly what allows the parameters to
                ; be measured again. Do it without being asked, and put the
                ; profile back the moment the configuration is usable, so the
                ; recovery is just: detect, done.
                (if motor-config-bad
                    (if (not profile-suspend) {
                            (profile-suspend-set 1)
                            (setq suspend-auto true)
                            (setq suspend-mode drive-mode)
                    })

                    ; The configuration also looks usable the instant the tool
                    ; resets it to defaults, which is the step immediately
                    ; before it measures. Putting the profile back there would
                    ; scale the current away again and the detection would fail
                    ; for the same reason as before. So wait to be told the
                    ; work is finished: selecting a drive mode does that, and
                    ; so does a power cycle, which clears this anyway.
                    (if (and profile-suspend
                             suspend-auto
                             (!= drive-mode suspend-mode))
                        (profile-suspend-set 0))
                )

                (if (and limits-stored
                         (> (secs-since display-ts) 5.0)
                         (< (abs (get-speed)) 0.5))
                    (if profile-last
                        (restore-limits)
                        ; Nothing applied and no display: the configuration is
                        ; the user's own again, so follow any changes they make
                        ; while it is unplugged rather than restoring stale
                        ; limits the next time one appears and goes away. Same
                        ; sanity check as the first capture -- a max scale of
                        ; zero is never something to adopt as the real setting.
                        (if (> (conf-get 'l-current-max-scale) 0.0)
                            (setq limits-stored (list
                                (conf-get 'l-current-min-scale)
                                (conf-get 'l-current-max-scale)
                                (conf-get 'l-min-erpm)
                                (conf-get 'l-max-erpm)
                            ))
                        )
                    )
                )

                (sleep 0.5)
        })

        (loopwhile-thd ("Therm" 200) t {
                (therm-loop)
                (sleep 0.1)
        })

        ; ---- Inokim OX light box ----
        ; Box pin 1 (red, 60 V) <- Switched VBUS V+ (AUX 2)
        ; Box pin 4 (green, headlight cmd, 3.3 V) <- STM32 AUX pin 5 (TX)
        ; Box pin 3 (yellow, rear/brake cmd, 3.3 V) <- STM32 AUX pin 6 (RX)
        ; Brake light (RX) on (steady or flashing) whenever the ADC2 brake is pulled.
        (set-aux 2 1)
        (gpio-configure 'pin-tx 'pin-mode-out)
        (gpio-configure 'pin-rx 'pin-mode-out)

        ; Automatic lights thread: DISABLED (no light sensor fitted)
        ;(loopwhile-thd ("AutoLight" 100) t {
        ;        (var v (get-adc 2))
        ;        (if (< v auto-light-on-v)
        ;            (setq dark-time (+ dark-time 0.5))
        ;            (setq dark-time 0.0))
        ;        (if (> v auto-light-off-v)
        ;            (setq bright-time (+ bright-time 0.5))
        ;            (setq bright-time 0.0))
        ;        (if (> dark-time auto-light-delay) (setq auto-dark 1))
        ;        (if (> bright-time auto-light-delay) (setq auto-dark 0))
        ;        (sleep 0.5)
        ;})

        (loopwhile-thd ("Lights" 100) t {
                ; Headlight + tail: follow the Dash lights button
                (gpio-write 'pin-tx (if (= light-on 1) 1 0))
                ; With light sensor (disabled): Dash button OR dark
                ;(gpio-write 'pin-tx
                ;    (if (or (= light-on 1)
                ;            (and (= auto-light-enabled 1) (= auto-dark 1)))
                ;        1 0))
                ; Rear/brake command:
                ; braking -> flashing 0/3.3 V (brake-flash = 1, default, like the
                ;            original controller) or steady 3.3 V (brake-flash = 0),
                ; otherwise -> steady 3.3 V with lights on, 0 V with lights off.
                (if (> (get-adc 1) brake-light-threshold)
                    (if (= brake-flash 1)
                        {
                            (gpio-write 'pin-rx 1)
                            (sleep brake-flash-period)
                            (gpio-write 'pin-rx 0)
                            (sleep brake-flash-period)
                        }
                        {
                            (gpio-write 'pin-rx 1)
                            (sleep 0.05)
                        }
                    )
                    {
                        (gpio-write 'pin-rx (if (= light-on 1) 1 0))
                        (sleep 0.05)
                    }
                )
        })

        (start-code-server)

        ; Wait for things to start up
        (sleep 10)

        ; Start logging at boot if configured
        (if (read-setting 'log-at-boot)
            (start-log
                (read-setting 'can-id)
                (read-setting 'append-gnss)
                (read-setting 'log-local)
                (read-setting 'log-can)
                (read-setting 'log-bms)
                (read-setting 'log-rate)
        ))
})

@const-end

(image-save)
(main)
