package com.nebula.app;

import android.annotation.SuppressLint;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

/**
 * Nébula (Android) — casca que abre a Nébula (que roda no servidor/host).
 *
 * O que este app faz:
 *  - mostra a Nébula num WebView em tela cheia;
 *  - guarda a chave do usuário (localStorage do site) entre as sessões;
 *  - tem um menu (engrenagem) para: recarregar, trocar endereço, limpar
 *    dados do site (cache/chave) e ver a versão;
 *  - tela de erro amigável quando o servidor não responde;
 *  - botão físico "voltar" navegando dentro da página.
 *
 * Padrão: aponta para o servidor público da Nébula. Como cada pessoa usa a
 * própria chave do Gemini, o usuário não precisa configurar nada.
 */
public class MainActivity extends AppCompatActivity {

    private static final String PREFS = "nebula";
    private static final String CHAVE_URL = "url";

    private WebView web;
    private LinearLayout erroView;
    private TextView erroTexto;
    private FrameLayout container;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        container = new FrameLayout(this);

        web = new WebView(this);
        container.addView(web, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));

        erroView = montarTelaDeErro();
        erroView.setVisibility(View.GONE);
        container.addView(erroView, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));

        container.addView(montarBotaoMenu());
        setContentView(container);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);       // localStorage: guarda a chave do usuário
        s.setDatabaseEnabled(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);

        // Guarda cookies entre as sessões (sessão do servidor).
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, true);

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri destino = request.getUrl();
                String host = destino.getHost() == null ? "" : destino.getHost();
                // Links de fora (outro site) abrem no navegador do aparelho.
                String proprio = Uri.parse(endereco()).getHost();
                if (proprio != null && !host.equals(proprio)) {
                    try {
                        startActivity(new Intent(Intent.ACTION_VIEW, destino));
                    } catch (Exception ignorado) {
                        Toast.makeText(MainActivity.this,
                                "Não consegui abrir este link.", Toast.LENGTH_SHORT).show();
                    }
                    return true;
                }
                view.loadUrl(destino.toString());
                return true;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                erroView.setVisibility(View.GONE);
                web.setVisibility(View.VISIBLE);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request,
                                        WebResourceError error) {
                if (request.isForMainFrame()) mostrarErro();
            }
        });

        // O WebView do Android IGNORA o atributo `download` do HTML: sem este
        // listener, tocar em "Baixar" num arquivo gerado pela Nébula não faz
        // NADA (o clique morre em silêncio). É o botão que mais faz falta — o
        // usuário quer o site no aparelho. Aqui o download é feito de verdade
        // e, ao terminar, o arquivo é aberto.
        web.setDownloadListener((url, userAgent, contentDisposition, mimeType, contentLength) -> {
            try {
                // Nome a partir do endereço (index.html, site.zip, ...).
                String nome = android.webkit.URLUtil.guessFileName(
                        url, contentDisposition, mimeType);
                DownloadManager.Request pedido = new DownloadManager.Request(Uri.parse(url));
                pedido.setMimeType(mimeType);
                pedido.setTitle(nome);
                pedido.setDescription("Baixando da Nébula…");
                pedido.setNotificationVisibility(
                        DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                // Fica visível na pasta Downloads do aparelho.
                pedido.setDestinationInExternalPublicDir(
                        android.os.Environment.DIRECTORY_DOWNLOADS, nome);
                DownloadManager gerente =
                        (DownloadManager) getSystemService(android.content.Context.DOWNLOAD_SERVICE);
                if (gerente != null) {
                    gerente.enqueue(pedido);
                    Toast.makeText(MainActivity.this,
                            "Baixando " + nome + "…", Toast.LENGTH_SHORT).show();
                } else {
                    abrirNoNavegador(url);
                }
            } catch (Exception falha) {
                // Sem permissão/pasta: abre no navegador do aparelho, que baixa.
                abrirNoNavegador(url);
            }
        });

        carregar();
    }

    /** Abre um endereço no navegador de fora (usado quando o WebView não dá conta). */
    private void abrirNoNavegador(String url) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (Exception ignorado) {
            Toast.makeText(this, "Não consegui baixar este arquivo.", Toast.LENGTH_SHORT).show();
        }
    }

    /** Botão de engrenagem flutuante, no canto superior direito. */
    private View montarBotaoMenu() {
        TextView engrenagem = new TextView(this);
        engrenagem.setText("⚙");
        engrenagem.setTextSize(22);
        engrenagem.setTextColor(Color.WHITE);
        engrenagem.setGravity(Gravity.CENTER);

        int tam = (int) (getResources().getDisplayMetrics().density * 40);
        int margem = (int) (getResources().getDisplayMetrics().density * 8);
        engrenagem.setBackgroundColor(0x66000000);

        FrameLayout.LayoutParams p = new FrameLayout.LayoutParams(tam, tam);
        p.gravity = Gravity.TOP | Gravity.END;
        p.topMargin = margem;
        p.rightMargin = margem;
        engrenagem.setLayoutParams(p);
        engrenagem.setAlpha(0.85f);
        engrenagem.setOnClickListener(v -> abrirMenu());
        return engrenagem;
    }

    /** Menu principal do app. */
    private void abrirMenu() {
        String[] opcoes = {
                "Recarregar a Nébula",
                "Trocar endereço do servidor",
                "Limpar dados do app (cache e chave)",
                "Sobre",
        };
        new AlertDialog.Builder(this)
                .setTitle("Nébula")
                .setItems(opcoes, (d, qual) -> {
                    switch (qual) {
                        case 0:
                            carregar();
                            break;
                        case 1:
                            pedirEndereco();
                            break;
                        case 2:
                            confirmarLimpeza();
                            break;
                        default:
                            mostrarSobre();
                            break;
                    }
                })
                .setNegativeButton("Fechar", null)
                .show();
    }

    /** Tela mostrada quando o servidor não responde. */
    private LinearLayout montarTelaDeErro() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setBackgroundColor(0xFF0B0B12);
        box.setGravity(Gravity.CENTER);
        int pad = (int) (getResources().getDisplayMetrics().density * 24);
        box.setPadding(pad, pad, pad, pad);

        TextView titulo = new TextView(this);
        titulo.setText("Nébula");
        titulo.setTextColor(0xFFFFFFFF);
        titulo.setTextSize(28);
        titulo.setGravity(Gravity.CENTER);
        box.addView(titulo);

        erroTexto = new TextView(this);
        erroTexto.setTextColor(0xFF9CA3AF);
        erroTexto.setTextSize(15);
        erroTexto.setGravity(Gravity.CENTER);
        erroTexto.setPadding(0, pad / 2, 0, pad);
        box.addView(erroTexto);

        Button tentar = new Button(this);
        tentar.setText("Tentar de novo");
        tentar.setOnClickListener(v -> carregar());
        box.addView(tentar);

        Button trocar = new Button(this);
        trocar.setText("Trocar endereço");
        trocar.setOnClickListener(v -> pedirEndereco());
        box.addView(trocar);

        return box;
    }

    private void mostrarErro() {
        String url = endereco();
        erroTexto.setText("Não consegui falar com a Nébula em:\n\n" + url
                + "\n\nConfira se o aparelho está com internet. "
                + "No plano grátis, o servidor pode levar até 1 minuto "
                + "para acordar no primeiro acesso.");
        web.setVisibility(View.GONE);
        erroView.setVisibility(View.VISIBLE);
    }

    private String endereco() {
        SharedPreferences p = getSharedPreferences(PREFS, MODE_PRIVATE);
        String padrao = getString(R.string.nebula_url);
        return p.getString(CHAVE_URL, padrao);
    }

    private void carregar() {
        erroView.setVisibility(View.GONE);
        web.setVisibility(View.VISIBLE);
        web.loadUrl(endereco());
    }

    /** Caixinha para trocar o endereço do servidor. */
    private void pedirEndereco() {
        EditText campo = new EditText(this);
        campo.setInputType(InputType.TYPE_TEXT_VARIATION_URI);
        campo.setText(endereco());
        campo.setHint("https://exemplo.onrender.com");

        LinearLayout caixa = new LinearLayout(this);
        caixa.setOrientation(LinearLayout.VERTICAL);
        int pad = (int) (getResources().getDisplayMetrics().density * 16);
        caixa.setPadding(pad, pad / 2, pad, 0);
        caixa.addView(campo);

        new AlertDialog.Builder(this)
                .setTitle("Endereço da Nébula")
                .setMessage("Onde a Nébula está rodando. Em geral não precisa mudar.")
                .setView(caixa)
                .setPositiveButton("Salvar", (d, w) -> {
                    String novo = campo.getText().toString().trim();
                    if (!novo.isEmpty() && !novo.startsWith("http")) {
                        novo = "https://" + novo;
                    }
                    if (!novo.isEmpty()) {
                        getSharedPreferences(PREFS, MODE_PRIVATE)
                                .edit().putString(CHAVE_URL, novo).apply();
                        Toast.makeText(this, "Endereço salvo", Toast.LENGTH_SHORT).show();
                    }
                    carregar();
                })
                .setNeutralButton("Restaurar padrão", (d, w) -> {
                    getSharedPreferences(PREFS, MODE_PRIVATE)
                            .edit().remove(CHAVE_URL).apply();
                    Toast.makeText(this, "Endereço padrão restaurado",
                            Toast.LENGTH_SHORT).show();
                    carregar();
                })
                .setNegativeButton("Cancelar", null)
                .show();
    }

    private void confirmarLimpeza() {
        new AlertDialog.Builder(this)
                .setTitle("Limpar dados do app?")
                .setMessage("Apaga o cache e a chave guardada. Você vai precisar "
                        + "colar a chave do Gemini de novo. As conversas ficam "
                        + "salvas no servidor.")
                .setPositiveButton("Limpar", (d, w) -> {
                    web.clearCache(true);
                    web.clearHistory();
                    CookieManager.getInstance().removeAllCookies(null);
                    CookieManager.getInstance().flush();
                    SharedPreferences.Editor e =
                            getSharedPreferences(PREFS, MODE_PRIVATE).edit();
                    e.remove(CHAVE_URL);
                    e.apply();
                    // Limpa o armazenamento do site (localStorage/IndexedDB).
                    web.clearFormData();
                    android.webkit.WebStorage.getInstance().deleteAllData();
                    Toast.makeText(this, "Dados limpos", Toast.LENGTH_SHORT).show();
                    carregar();
                })
                .setNegativeButton("Cancelar", null)
                .show();
    }

    private void mostrarSobre() {
        String versao = "1.0";
        try {
            versao = getPackageManager()
                    .getPackageInfo(getPackageName(), 0).versionName;
        } catch (Exception ignorado) {
            // mantém o padrão
        }
        new AlertDialog.Builder(this)
                .setTitle("Sobre a Nébula")
                .setMessage("Versão " + versao
                        + "\n\nA Nébula é um assistente de IA. Este app abre a "
                        + "Nébula que roda no servidor.\n\nVocê usa a sua "
                        + "própria chave do Gemini — ela fica só no seu aparelho. "
                        + "Pegue a sua, de graça, em aistudio.google.com/apikey.")
                .setPositiveButton("Entendi", null)
                .show();
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK && web.canGoBack()) {
            web.goBack();
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }
}
