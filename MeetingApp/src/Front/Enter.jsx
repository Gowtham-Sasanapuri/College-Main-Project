import React from "react";
import Navbar from "./components/Navbar/Navbar";
import Content from "./components/C_Content/Content";
import MeetingCards from "./components/Cards/MeetingCards";
import styles from "./Enter.module.css";

export default function Enter() {
    return (
        <div className={styles.page}>
            <Navbar />
            <Content />
            <MeetingCards />
        </div>
    );
}