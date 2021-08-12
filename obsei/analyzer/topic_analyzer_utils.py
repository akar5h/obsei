import logging
from abc import abstractmethod
from typing import Any, Dict, List, Tuple
from symspellpy import SymSpell, Verbosity
from obsei.payload import TextPayload

import umap.umap_ as umap
import numpy as np
from sklearn.feature_extraction.text import CountVectorizer
import pandas as pd
import hdbscan

def get_umap_embedings(embeddings, n_neighbors, n_component):
    return umap.UMAP(n_neighbors=n_neighbors,
                            n_components=n_component,
                            metric='cosine').fit_transform(embeddings)

def cluster_embeddings(embeddings, min_cluster_size):
    return hdbscan.HDBSCAN(min_cluster_size=min_cluster_size,
                          metric='euclidean',
                          cluster_selection_method='eom').fit(embeddings)


def get_topics_by_cluster(docs, cluster, source_name):
    docs_df = pd.DataFrame(docs, columns=["text"])
    docs_df['topic'] = cluster.labels_
    docs_df['doc_id'] = range(len(docs_df))
    docs_per_topic = docs_df.groupby(['topic'], as_index = False)
    docs_per_topic_agg = docs_per_topic.agg({'text': ' '.join})

    top_n_words_list = []
    tf_idf, count = c_tf_idf(docs_per_topic_agg.text.values, m=len(docs))
    top_n_words = extract_top_n_words_per_topic(tf_idf, count, docs_per_topic_agg, n=20) #todo, can add to filter out stopwords
    topic_sizes = extract_topic_sizes(docs_df)

    top_k = 5
    top_n_words_dict = {}
    for c_no, value in top_n_words.items():
        if c_no == -1:
            top_n_words_dict[-1] = "~OUTLIERS~"
        cluster = sorted(value, key=lambda x: x[1])
        top_n_words_dict[c_no] = "_".join([i for i,j in cluster[-top_k:]])

    for name, group in docs_per_topic:

        payload = TextPayload(
            processed_text=top_n_words_dict[name],
            meta={"cluster_size": topic_sizes[name], "cluster_topics" :top_n_words_dict[name]},
            segmented_data={
                "cluster_texts": [
                    TextPayload(
                        processed_text = t,
                        meta = {"cluster_id": name}
                    )
                for t in group["text"]]
            },
            source_name = source_name
        )
        top_n_words_list.append(payload)


    return top_n_words_list #return a list of textpayloads?

def c_tf_idf(documents, m, ngram_range=(1, 1)):
    count = CountVectorizer(ngram_range=ngram_range, stop_words="english").fit(documents)
    t = count.transform(documents).toarray()
    w = t.sum(axis=1)
    tf = np.divide(t.T, w)
    sum_t = t.sum(axis=0)
    idf = np.log(np.divide(m, sum_t)).reshape(-1, 1)
    tf_idf = np.multiply(tf, idf)

    return tf_idf, count




def extract_top_n_words_per_topic(tf_idf, count, docs_per_topic, n=20):
    words = count.get_feature_names()
    labels = list(docs_per_topic.topic)
    tf_idf_transposed = tf_idf.T
    indices = tf_idf_transposed.argsort()[:, -n:]
    top_n_words = {label: [(words[j], tf_idf_transposed[i][j]) for j in indices[i]][::-1] for i, label in enumerate(labels)}
    return top_n_words

def extract_topic_sizes(df):
    topic_sizes = (df.groupby(['topic'])
                     .text
                     .count()
                     .reset_index()
                     .rename({"topic": "topic", "text": "Size"}, axis='columns')
                     .sort_values("Size", ascending=False)).to_numpy()
    return {key:value for key, value in topic_sizes}


