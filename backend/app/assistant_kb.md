# What the tool does
keywords: ماذا تفعل الأداة، فكرة الأداة، الغرض من الأداة / what does the tool do, purpose of the tool
تحقّق أداة تتحقق من الحديث قبل نشره. تأخذ نصًا أو صورة منشور أو رابطًا، وتبحث عن النص في المصادر المعتمدة، وتعرض حكم العلماء المسجّل بنصّه مع المصدر والرقم والروابط. الأداة لا تُصدر حكمًا من عندها، وإذا لم تجد مرجعًا موثوقًا تمتنع وتقول ذلك.
Tahaqqaq verifies a hadith before you publish it. It takes a text, a screenshot or a link, finds the saying in approved sources, and shows the ruling scholars recorded for it, word for word, with the source, number and links. The tool never issues a ruling of its own; when there is no reliable match it abstains and says so.

# Sources
keywords: مصادر، مصدر، المصادر المعتمدة، الدرر السنية، الكتب الستة، القرآن، الجمهرة، قاعدة البيانات، من أين / sources, dorar, six books, quran, database, where from
المصادر: الموسوعة الحديثية في الدرر السنية لأحكام العلماء وشروح الأحاديث، ونصوص الكتب الستة مع أحكام المحققين، والقرآن الكريم برسم مصحف المدينة مع روابط الموسوعة القرآنية، وموسوعة التفسير في الدرر للشرح الموسّع للآيات، والجمهرة لتعريفات المصطلحات. وتضم القاعدة ٣٤٬١٥٣ حديثًا و٦٬٢٣٦ آية وقائمة من الأقوال المنتشرة بأحكامها المنقولة من الدرر.
Sources: the Hadith Encyclopedia of Dorar.net for scholars' rulings and explanations, the texts of the Six Books with their editors' grades, the Qur'an in the Madinah Mushaf script with quranpedia links, Dorar's Tafsir Encyclopedia for verse explanations, and Al-Jamhara for definitions of terms. The database holds 34,153 hadiths, 6,236 verses and a list of circulated sayings with rulings quoted from Dorar.

# Result states
keywords: حالات، الحالة، مؤيد، مؤيد جزئيا، غير مؤكد، امتناع، يمتنع، إحالة، معنى النتيجة / states, result, confirmed, partial, uncertain, abstain, referral
حالات النتيجة: «مؤيَّد بمصدر» حين يطابق النص مصدرًا معتمدًا. «مؤيَّد جزئيًا – اختلاف رواية» حين يطابق المعنى مع اختلاف بعض الألفاظ. «غير مؤكد» حين لا يوجد نص بهذا اللفظ ويُعرض أقرب نص فقط ولا يُنسب حكمه إلى ما أدخلته. «وُجد النص وحكمه ضعيف أو موضوع» حين يوجد النص لكن حكمه لا يصح. «لا مرجع – يُمتنع» حين لا يوجد مرجع موثوق. «إحالة» حين يكون السؤال فتوى شخصية تُحال إلى أهل العلم.
Result states: "confirmed" when the text matches an approved source; "partially confirmed – variant wording" when the meaning matches with some words different; "uncertain" when no text has this wording and only the closest text is shown, whose ruling does not apply to your input; "found, weak or fabricated" when the text exists but its ruling is not authentic; "abstain" when there is no reliable source; "referral" when the question is a personal fatwa, referred to scholars.

# Confidence and acceptance threshold
keywords: نسبة الثقة، الثقة، حد القبول، النسبة، الرقم / confidence, percentage, threshold, score
نسبة الثقة رقم من صفر إلى مئة يقيس قرب النص من المصدر لفظًا ومعنى. تسعون فأكثر «مؤيَّد بمصدر»، وخمسة وسبعون فأكثر «مؤيَّد جزئيًا»، وخمسون فأكثر «غير مؤكد» أي أقرب نص فقط، وما دون ذلك امتناع. ونسبة الثقة لا تعني صحة الحديث، فالصحة يحددها حكم العلماء المسجّل.
Confidence is a number from 0 to 100 that measures how close the text is to the source in wording and meaning. 90 or more is "confirmed", 75 or more "partially confirmed", 50 or more "uncertain" (closest text only), below that the tool abstains. Confidence does not mean authenticity: authenticity is the recorded ruling of the scholars.

# How matching works
keywords: المطابقة، كيف تعمل، كيف يبحث، البحث، الخوارزمية، التشكيل / matching, how it works, search, algorithm, diacritics
المطابقة على مراحل: مطابقة حرفية، ثم تشابه الحروف، ثم تشابه المعنى بشرط وجود ألفاظ مشتركة، وإلا امتناع. ويُوحَّد النص قبل البحث بحذف التشكيل وتوحيد الهمزات والياء والتاء المربوطة. والاقتباس العربي القصير يجب أن توجد كل كلماته ليُؤكَّد.
Matching runs in stages: exact match, then character similarity, then meaning similarity that still needs shared wording, otherwise abstain. Text is normalised first: diacritics removed, alef forms, ya and ta marbuta unified. A short Arabic quote must contain every one of its words to be confirmed.

# Where AI is used
keywords: الذكاء الاصطناعي، النموذج، نماذج لغوية، الآلة / artificial intelligence, ai, model, llm, machine
الذكاء الاصطناعي يُستخدم في مهام محددة: قراءة الصور، واستخلاص المقاطع المقتبسة من النصوص الطويلة، وترجمة اللغات الأخرى للمطابقة فقط، والتأكد من أن النص المطابق هو الرواية نفسها، وكتابة شرح موجز يُفحص، وشرح موسّع ملخّص من شروح الدرر وحدها، وتحويل الصوت إلى نص في هذا المساعد. ولا يُصدر أي نموذج حكمًا على حديث أبدًا.
AI is used for specific tasks: reading images, extracting quoted segments from long texts, translating other languages for matching only, checking that a matched record is the same report, writing a fact-checked brief explanation, an extended explanation summarised only from Dorar's commentaries, and turning speech into text in this assistant. No model ever issues a ruling on a hadith.

# Narrations in other books
keywords: الروايات، روايات، مواضع أخرى، كتب أخرى / narrations, other books, other places
الرواية نفسها في مواضع أخرى: يعرض التقرير النص نفسه في كتب أخرى أو بأرقام أخرى، ولكل موضع حكمه المسجّل.
The report lists the same text in other books or under other numbers, each with its own recorded ruling.

# Languages and voice
keywords: اللغات، اللغة، الصوت، التسجيل، الميكروفون، الترجمة / languages, language, voice, speech, microphone, translation
النصوص العربية والإنجليزية تُطابق مباشرة، وأي لغة أخرى تُترجم آليًا للمطابقة فقط مع تنبيه. وفي هذا المساعد يُقبل الصوت بالعربية والإنجليزية فقط، ويظهر النص المسموع لتؤكده قبل التحقق، وإذا لم يكن السماع واضحًا يعتذر المساعد بدل أن يخمّن.
Arabic and English texts are matched directly; any other language is machine-translated for matching only, with a notice. In this assistant, voice is accepted in Arabic and English only; the transcript is shown for you to confirm before verification, and when the speech is not clear the assistant says so instead of guessing.

# Privacy
keywords: الخصوصية، الحفظ، التخزين، هل تحفظ، البيانات / privacy, storage, do you store, data
لا تُحفظ النصوص ولا الصور ولا التسجيلات على الخادم. سجل التحقق والمحادثة يبقيان في متصفحك خلال الجلسة فقط. ويُرسل الصوت إلى خدمة تحويل الكلام إلى نص ولا يُحفظ.
Texts, images and recordings are not stored on the server. Your history and this conversation stay in your browser for the session only. Voice is sent to the speech-to-text service and not stored.

# PDF and share image
keywords: PDF، تصدير، صورة، مشاركة، حفظ التقرير / pdf, export, image, share, save report
يمكن تصدير التقرير PDF بالعربية أو الإنجليزية، أو حفظه صورة للمشاركة تحمل الحكم المنقول ومصدره والتنبيه، لتصحيح منشور متداول.
A report can be exported as a PDF in Arabic or English, or saved as an image to share, carrying the recorded ruling, its source and the disclaimer, to correct a circulating post.

# Limits
keywords: الحدود، القيود، لا يغطي، مسند أحمد، الموطأ، روابط، إنستغرام / limits, coverage, not covered, links, instagram
تغطي القاعدة الكتب الستة والقرآن وقائمة الأقوال المنتشرة. والحديث الموجود في كتب أخرى فقط كمسند أحمد والموطأ قد لا يُطابق، فتمتنع الأداة وتعرض رابط البحث في الدرر. ولا تُقرأ روابط إنستغرام وفيسبوك ويوتيوب وتيك توك، والصق النص أو صورة المنشور بدلًا منها.
The database covers the Six Books, the Qur'an and the list of circulated sayings. A hadith found only in other collections, such as Musnad Ahmad or the Muwatta, may not be matched; the tool abstains and offers a Dorar search link. Instagram, Facebook, YouTube and TikTok links cannot be read; paste the text or a screenshot instead.

# Measured accuracy
keywords: الدقة، القياس، نسبة النجاح، الاختبار، موثوقية / accuracy, measured, benchmark, results, reliability
في مجموعة القاعدة من ٩٨ مُدخلًا وُجد الحديث الصحيح في كل الحالات، وامتنعت الأداة عن كل النصوص المختلقة. وفي خمسين نصًا متداولًا من وسائل التواصل أُكّدت كل الأحاديث الصحيحة، ولم يُعرض أي نص موضوع على أنه صحيح. وفي اختبار صوتي بأصوات مولّدة قادت التسجيلات العربية إلى الحديث الصحيح في عشرين من عشرين.
On the 98-input corpus set the right hadith was found in every case and every invented text was refused. On fifty sayings circulating on social media, every authentic hadith was confirmed and no fabricated saying was shown as authentic. In a voice test with synthetic voices, the Arabic recordings led to the right hadith in twenty of twenty.

# The assistant
keywords: المساعد، من أنت، ماذا تستطيع، حدودك / assistant, who are you, what can you do, scope
هذا المساعد مخصص لثلاثة أمور: التحقق من حديث تكتبه أو تقوله، وشرح التقرير المفتوح أمامك، والإجابة عن أسئلة هذه الأداة. ولا يجيب عن الأسئلة الدينية العامة ولا يُفتي، ويحيل الأسئلة الشخصية إلى أهل العلم.
This assistant does three things: verify a hadith you type or say, explain the report open in front of you, and answer questions about this tool. It does not answer general religious questions or give fatwas; personal questions are referred to scholars.
