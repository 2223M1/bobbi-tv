package org.bobbi.helper;

import android.content.Context;
import android.content.SharedPreferences;
import android.content.res.Configuration;
import java.util.Locale;

/**
 * App-scoped UI locale preference for standalone bobbi Helper.
 *
 * Defaults to Simplified Chinese ("zh") when no explicit preference is saved,
 * preserves explicit user selection ("zh" or "en") across restarts, and never
 * mutates Android system locale or the JVM default locale.
 */
final class AppLocale {
    private static final String PREFS_NAME = "bobbi_locale";
    private static final String KEY_UI_LANG = "ui_lang";
    static final String LANG_ZH = "zh";
    static final String LANG_EN = "en";

    private AppLocale() {}

    static String normalize(String raw) {
        if (raw == null) return LANG_ZH;
        String lower = raw.trim().toLowerCase(Locale.ROOT);
        if (lower.startsWith("en") || lower.startsWith("resource.language.en")) return LANG_EN;
        return LANG_ZH;
    }

    static String getLanguage(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        String saved = prefs.getString(KEY_UI_LANG, "");
        if (saved == null || saved.isEmpty()) return LANG_ZH;
        return normalize(saved);
    }

    static boolean setLanguage(Context context, String language) {
        String target = normalize(language);
        String current = getLanguage(context);
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                .edit()
                .putString(KEY_UI_LANG, target)
                .apply();
        return !target.equals(current);
    }

    static Locale localeFor(String language) {
        return LANG_EN.equals(normalize(language)) ? Locale.ENGLISH : Locale.SIMPLIFIED_CHINESE;
    }

    static Context wrap(Context base) {
        if (base == null) return null;
        Locale target = localeFor(getLanguage(base));
        Configuration config = new Configuration(base.getResources().getConfiguration());
        config.setLocale(target);
        config.setLayoutDirection(target);
        return base.createConfigurationContext(config);
    }
}
