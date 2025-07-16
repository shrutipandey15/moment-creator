class PoemPlayer {
  constructor(momentData, appBaseUrl) {
    this.audioElement = document.getElementById("poemAudio");
    this.playPauseBtn = document.getElementById("playPauseBtn");
    this.playIcon = document.getElementById("playIcon");
    this.pauseIcon = document.getElementById("pauseIcon");
    this.progressRail = document.getElementById("progressRail");
    this.progressFill = document.getElementById("progressFill");
    this.currentTimeEl = document.getElementById("currentTime");
    this.durationEl = document.getElementById("duration");
    this.poemTextContainer = document.querySelector(".poem-text");
    this.shareBtn = document.getElementById("shareBtn");
    this.clearSelectionBtn = document.getElementById("clearSelectionBtn");
    this.shareModal = document.getElementById("share-modal");
    this.closeModalBtn = document.getElementById("close-modal-btn");
    this.sharedLinesPreview = document.getElementById("shared-lines-preview");
    this.shareMessageInput = document.getElementById("share-message");
    this.generateShareLinkBtn = document.getElementById(
      "generate-share-link-btn"
    );
    this.finalLinkInput = document.getElementById("final-link");
    this.personalMessageDisplay = document.getElementById(
      "personal-message-display"
    );
    this.momentPopup = document.getElementById("moment-popup");
    this.popupMessage = document.getElementById("popup-message");
    this.popupLyric = document.getElementById("popup-lyric");
    this.selectionInfo = document.getElementById("selection-info");
    this.selectionCount = document.getElementById("selection-count");
    this.personalMessagePreview = document.getElementById(
      "personal-message-preview"
    );
    this.speechBubbleText = document.getElementById("speech-bubble-text");

    this.poemData = momentData;
    this.appBaseUrl = appBaseUrl;
    this.poemLines = [];
    this.currentLineIndex = -1;
    this.selectedLines = new Set();
    this.specialMoments = [];
    this.isPopupVisible = false;
    this.boundHidePopup = null;
    this.doodlePaths = [];
    this.hasAnimatedDoodles = false;
    this.poemData = momentData;

    this.init();
  }

  init() {
    this.populatePoemText();
    this.addEventListeners();

    if (this.audioElement.readyState > 0) {
      this.setDuration();
    }

    this.checkForSharedMoment();
  }

  populatePoemText() {
    if (!this.poemData.lyrics || this.poemData.lyrics.length === 0) {
      this.poemTextContainer.innerHTML =
        '<p class="no-lyrics">No lyrics were available for this moment.</p>';
      return;
    }
    this.poemData.lyrics.forEach((line) => {
      const span = document.createElement("span");
      span.classList.add("poem-line");
      span.textContent = line || "...";
      this.poemTextContainer.appendChild(span);
    });
    this.poemLines = this.poemTextContainer.querySelectorAll(".poem-line");
  }

  addEventListeners() {
    this.playPauseBtn.addEventListener("click", () => this.togglePlay());
    this.progressRail.addEventListener("click", (e) => this.seek(e));
    this.audioElement.addEventListener("timeupdate", () => this.updateUI());
    this.audioElement.addEventListener("loadedmetadata", () =>
      this.setDuration()
    );
    this.audioElement.addEventListener("ended", () => this.resetPlayer());
    this.audioElement.addEventListener("play", () =>
      this.updatePlayPauseIcons(true)
    );
    this.audioElement.addEventListener("pause", () =>
      this.updatePlayPauseIcons(false)
    );
    this.shareBtn.addEventListener("click", () => this.openShareModal());
    this.clearSelectionBtn.addEventListener("click", () =>
      this.clearSelection()
    );
    this.closeModalBtn.addEventListener("click", () => this.closeShareModal());
    this.generateShareLinkBtn.addEventListener("click", () =>
      this.generateShareLink()
    );

    this.poemLines.forEach((line, index) => {
      line.addEventListener("click", () => this.toggleLineSelection(index));
    });
    this.shareMessageInput.addEventListener("input", () => {
      const message = this.shareMessageInput.value;
      if (message.trim() !== "") {
        this.speechBubbleText.textContent = `“${message}”`;
        this.personalMessagePreview.style.display = "block";
      } else {
        this.personalMessagePreview.style.display = "none";
      }
    });
  }

  togglePlay() {
    if (this.audioElement.paused || this.audioElement.ended) {
      this.audioElement
        .play()
        .catch((e) => console.error("Autoplay failed:", e));
    } else {
      this.audioElement.pause();
    }
  }

  seek(e) {
    const railRect = this.progressRail.getBoundingClientRect();
    this.audioElement.currentTime =
      ((e.clientX - railRect.left) / this.progressRail.clientWidth) *
      this.audioElement.duration;
  }

  resetPlayer() {
    this.updatePlayPauseIcons(false);
    this.clearActiveLines();
  }

  updateUI() {
    if (isNaN(this.audioElement.duration)) return;
    const progressPercent =
      (this.audioElement.currentTime / this.audioElement.duration) * 100;
    this.progressFill.style.width = `${progressPercent}%`;
    this.currentTimeEl.textContent = this.formatTime(
      this.audioElement.currentTime
    );
    this.updateActiveLine();
  }

  setDuration() {
    this.durationEl.textContent = this.formatTime(this.audioElement.duration);
  }

  updatePlayPauseIcons(isPlaying) {
    this.playIcon.style.display = isPlaying ? "none" : "block";
    this.pauseIcon.style.display = isPlaying ? "block" : "none";
  }

  updateActiveLine() {
    const currentTime = this.audioElement.currentTime + 0.1;
    let activeLineIndex = -1;

    for (let i = 0; i < this.poemData.timings.length; i++) {
      const timing = this.poemData.timings[i];
      if (
        timing &&
        timing.end > 0 &&
        currentTime >= timing.start &&
        currentTime < timing.end
      ) {
        activeLineIndex = i;
        break;
      }
    }

    if (activeLineIndex !== this.currentLineIndex) {
      this.clearActiveLines();
      if (activeLineIndex !== -1 && this.poemLines[activeLineIndex]) {
        const activeLine = this.poemLines[activeLineIndex];
        activeLine.classList.add("active");
        activeLine.scrollIntoView({ behavior: "smooth", block: "center" });
      }
      this.currentLineIndex = activeLineIndex;
    }

    this.checkForPopupTrigger(this.audioElement.currentTime);
  }

  clearActiveLines() {
    this.poemLines.forEach((line) => line.classList.remove("active"));
    this.currentLineIndex = -1;
  }

  formatTime(seconds) {
    if (isNaN(seconds)) return "0:00";
    const minutes = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${minutes}:${secs.toString().padStart(2, "0")}`;
  }

  toggleLineSelection(index) {
    if (this.selectedLines.has(index)) {
      this.selectedLines.delete(index);
      this.poemLines[index].classList.remove("selected");
    } else {
      this.selectedLines.add(index);
      this.poemLines[index].classList.add("selected");
    }
    this.updateSelectionUI();
  }

  clearSelection() {
    this.selectedLines.clear();
    this.poemLines.forEach((line) => line.classList.remove("selected"));
    this.updateSelectionUI();
  }

  updateSelectionUI() {
    const count = this.selectedLines.size;
    this.selectionCount.textContent = `${count} line${
      count !== 1 ? "s" : ""
    } selected`;
    this.selectionInfo.classList.toggle("visible", count > 0);
    this.clearSelectionBtn.classList.toggle("visible", count > 0);
  }

  openShareModal() {
    if (this.selectedLines.size === 0) {
      alert("Please click on lines to select them before sharing.");
      return;
    }
    this.updateSharedLinesPreview();
    this.shareModal.classList.add("visible");
  }

  closeShareModal() {
    this.shareModal.classList.remove("visible");
  }

  updateSharedLinesPreview() {
    const selectedLinesArray = Array.from(this.selectedLines).sort(
      (a, b) => a - b
    );
    this.sharedLinesPreview.innerHTML = selectedLinesArray
      .map(
        (index) =>
          `<div class="shared-line-item">“${this.poemData.lyrics[index]}”</div>`
      )
      .join("");
  }

  generateShareLink() {
    const selectedLinesArray = Array.from(this.selectedLines).sort(
      (a, b) => a - b
    );
    const dataToShare = {
      m: this.shareMessageInput.value,
      lines: selectedLinesArray,
    };
    const encodedData = btoa(
      unescape(encodeURIComponent(JSON.stringify(dataToShare)))
    );
    const shareableLink = `${this.appBaseUrl}/moment/${this.poemData.id}?data=${encodedData}`;

    this.finalLinkInput.value = shareableLink;
    this.finalLinkInput.select();
    navigator.clipboard
      .writeText(shareableLink)
      .then(() => {
        this.generateShareLinkBtn.textContent = "Copied!";
        setTimeout(() => {
          this.generateShareLinkBtn.textContent = "Generate & Copy Link";
        }, 2000);
      })
      .catch(() => {
        this.generateShareLinkBtn.textContent = "Could not copy";
      });
  }

  checkForSharedMoment() {
    const data = new URLSearchParams(window.location.search).get("data");
    if (!data) return;

    try {
      const sharedData = JSON.parse(decodeURIComponent(escape(atob(data))));
      if (sharedData.lines && sharedData.lines.length > 0) {
        sharedData.lines.sort((a, b) => a - b);
        this.specialMoments.push({
          lines: sharedData.lines,
          message: sharedData.m || "Someone shared these lines with you...",
        });
        this.personalMessageDisplay.textContent = `A special moment was shared with you...`;
        sharedData.lines.forEach((lineIndex) => {
          this.poemLines[lineIndex]?.classList.add("special-moment");
        });
      }
    } catch (e) {
      console.error("Could not parse share data.", e);
    }
  }

  checkForPopupTrigger(currentTime) {
    this.specialMoments.forEach((moment) => {
      const firstLineIndex = moment.lines[0];
      const lastLineIndex = moment.lines[moment.lines.length - 1];
      const momentStartTime = this.poemData.timings[firstLineIndex]?.start;
      const momentEndTime = this.poemData.timings[lastLineIndex]?.end;

      if (momentStartTime === undefined || momentEndTime === undefined) return;

      const isWithinMomentTime =
        currentTime >= momentStartTime && currentTime <= momentEndTime;

      if (isWithinMomentTime && !this.isPopupVisible) {
        this.showMomentPopup(moment);
      } else if (!isWithinMomentTime && this.isPopupVisible) {
        this.hideMomentPopup();
      }
    });
  }

  showMomentPopup(moment) {
    if (this.isPopupVisible) return;
    this.isPopupVisible = true;
    this.popupMessage.textContent = moment.message;
    this.popupLyric.textContent = `“${moment.lines
      .map((index) => this.poemData.lyrics[index])
      .join(" • ")}”`;
    this.momentPopup.classList.add("visible");

    this.boundHidePopup = this.hideMomentPopup.bind(this);
    setTimeout(
      () => document.addEventListener("click", this.boundHidePopup),
      100
    );
  }

  hideMomentPopup() {
    if (!this.isPopupVisible) return;
    this.isPopupVisible = false;
    this.momentPopup.classList.remove("visible");
    if (this.boundHidePopup) {
      document.removeEventListener("click", this.boundHidePopup);
      this.boundHidePopup = null;
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  if (typeof momentData !== "undefined" && typeof appBaseUrl !== "undefined") {
    new PoemPlayer(momentData, appBaseUrl);
  }
});
