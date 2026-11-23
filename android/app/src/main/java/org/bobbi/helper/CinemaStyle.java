package org.bobbi.helper;

import android.animation.ValueAnimator;
import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.StateListDrawable;
import android.view.Gravity;
import android.view.animation.DecelerateInterpolator;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

/** New-cinema palette, typography and reversible focus motion shared by setup screens. */
final class CinemaStyle {
    private final Context context;
    private final Typeface regular;
    private final Typeface bold;
    static final int FOCUS_MILLIS = 140;
    static final float FOCUS_SCALE = 1.02f;

    CinemaStyle(Context context) {
        this.context = context;
        regular = Typeface.createFromAsset(context.getAssets(), "fonts/HarmonyOS_SansSC_Regular.ttf");
        bold = Typeface.createFromAsset(context.getAssets(), "fonts/HarmonyOS_SansSC_Bold.ttf");
    }

    int dp(int value) { return Math.round(value * context.getResources().getDisplayMetrics().density); }
    int color(int id) { return context.getColor(id); }

    TextView text(String value, int size, boolean heading, int color) {
        TextView view = new TextView(context);
        view.setText(value);
        view.setTextSize(size);
        view.setTextColor(color(color));
        view.setTypeface(heading ? bold : regular);
        view.setLineSpacing(dp(3), 1.05f);
        view.setPadding(0, dp(6), 0, dp(10));
        return view;
    }

    GradientDrawable shape(int fill, int line) {
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(color(fill));
        shape.setCornerRadius(dp(14));
        shape.setStroke(dp(1), color(line));
        return shape;
    }

    LinearLayout column() {
        LinearLayout view = new LinearLayout(context);
        view.setOrientation(LinearLayout.VERTICAL);
        view.setClipChildren(false);
        view.setClipToPadding(false);
        return view;
    }

    Button button(LinearLayout parent, String label) {
        Button view = new Button(context);
        view.setText(label);
        view.setAllCaps(false);
        view.setTypeface(bold);
        view.setTextSize(19);
        view.setLetterSpacing(0);
        view.setGravity(Gravity.CENTER_VERTICAL | Gravity.START);
        view.setMinHeight(dp(56));
        view.setPadding(dp(20), dp(12), dp(20), dp(12));
        view.setBackgroundTintList(null);
        view.setStateListAnimator(null);
        int[][] states = {new int[]{-android.R.attr.state_enabled}, new int[]{android.R.attr.state_focused},
                new int[]{android.R.attr.state_pressed}, new int[]{}};
        view.setTextColor(new ColorStateList(states, new int[]{color(R.color.cinema_disabled),
                color(R.color.cinema_bg), color(R.color.cinema_bg), color(R.color.cinema_text)}));
        StateListDrawable backgrounds = new StateListDrawable();
        backgrounds.addState(states[0], shape(R.color.cinema_surface, R.color.cinema_line));
        backgrounds.addState(states[1], shape(R.color.cinema_focus, R.color.cinema_focus));
        backgrounds.addState(states[2], shape(R.color.cinema_focus, R.color.cinema_focus));
        backgrounds.addState(states[3], shape(R.color.cinema_surface_hi, R.color.cinema_line));
        view.setBackground(backgrounds);
        view.setOnFocusChangeListener((item, focused) -> {
            item.animate().cancel();
            float scale = focused && item.isEnabled() ? FOCUS_SCALE : 1f;
            if (ValueAnimator.areAnimatorsEnabled()) {
                item.animate().scaleX(scale).scaleY(scale).setDuration(FOCUS_MILLIS)
                        .setInterpolator(new DecelerateInterpolator()).start();
            } else { item.setScaleX(scale); item.setScaleY(scale); }
        });
        LinearLayout.LayoutParams size = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        size.setMargins(dp(3), dp(5), dp(3), dp(5));
        parent.addView(view, size);
        return view;
    }
}
